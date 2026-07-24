"""Crosswalk, provenance, and an end-to-end smoke test.

The crosswalk tests matter because many-to-one aggregation is the step most
likely to be silently wrong: a simple mean over O*NET-SOC codes weights a tiny
occupation the same as a huge one, which biases exposure for exactly the large
CPS categories that carry most of the tax base.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from fiscal_exposure.analysis import (
    amplification,
    assign_contrast_groups,
    base_shares,
)
from fiscal_exposure.crosswalk import map_exposure_to_cps, soc6_from_onet
from fiscal_exposure.provenance import Manifest, file_digest
from fiscal_exposure.synthetic import write_all
from fiscal_exposure.tax import TaxParams, compute_taxes


def test_soc6_reduction():
    s = pd.Series(["15-1251.00", "29-1141.03", "11-1011"])
    assert soc6_from_onet(s).tolist() == ["15-1251", "29-1141", "11-1011"]


def test_many_to_one_uses_employment_weights():
    """Two O*NET codes map to one CPS code; the big one must dominate."""
    exposure = pd.DataFrame(
        {"occ_code": ["15-1251.00", "15-1252.00"], "exposure": [0.9, 0.1]}
    )
    crosswalk = pd.DataFrame(
        {
            "from_code": ["15-1251.00", "15-1252.00"],
            "to_code": ["1000", "1000"],
            "weight": [900.0, 100.0],
        }
    )
    mapping, _ = map_exposure_to_cps(exposure, crosswalk)
    assert mapping.loc[0, "exposure"] == pytest.approx(0.9 * 0.9 + 0.1 * 0.1)
    assert mapping.loc[0, "exposure_unweighted"] == pytest.approx(0.5)
    assert mapping.loc[0, "n_source_codes"] == 2


def test_coverage_reports_unmapped_occupations_honestly():
    exposure = pd.DataFrame({"occ_code": ["15-1251.00"], "exposure": [0.8]})
    crosswalk = pd.DataFrame(
        {"from_code": ["15-1251.00"], "to_code": ["1000"], "weight": [1.0]}
    )
    universe = pd.Series(["1000", "2000", "3000", "4000"])
    employment = pd.Series(
        [900.0, 50.0, 30.0, 20.0], index=["1000", "2000", "3000", "4000"]
    )

    _, report = map_exposure_to_cps(
        exposure, crosswalk, cps_universe=universe, employment=employment
    )
    assert report.n_target_codes == 4
    assert report.n_mapped_target_codes == 1
    assert report.code_coverage == pytest.approx(0.25)
    # Only 1 of 4 codes, but 90% of workers: reporting both is the point.
    assert report.employment_covered == pytest.approx(0.9)
    assert set(report.unmapped_examples) == {"2000", "3000", "4000"}


def test_disjoint_codes_raise_rather_than_return_empty():
    exposure = pd.DataFrame({"occ_code": ["15-1251.00"], "exposure": [0.8]})
    crosswalk = pd.DataFrame(
        {"from_code": ["99-9999.00"], "to_code": ["1000"], "weight": [1.0]}
    )
    with pytest.raises(ValueError, match="share no codes"):
        map_exposure_to_cps(exposure, crosswalk)


def test_zero_weight_group_falls_back_to_equal_weights():
    exposure = pd.DataFrame(
        {"occ_code": ["a", "b"], "exposure": [0.2, 0.8]}
    )
    crosswalk = pd.DataFrame(
        {"from_code": ["a", "b"], "to_code": ["X", "X"], "weight": [0.0, 0.0]}
    )
    mapping, _ = map_exposure_to_cps(exposure, crosswalk)
    assert mapping.loc[0, "exposure"] == pytest.approx(0.5)


def test_manifest_round_trip(tmp_path):
    path = tmp_path / "manifest.json"
    target = tmp_path / "artifact.csv"
    target.write_text("a,b\n1,2\n")

    m = Manifest(path)
    with m.step("test_step", params={"k": 1}) as rec:
        rec.add_input(target)
        rec.add_output(target)
        rec.metric("coverage", 0.97)

    records = json.loads(path.read_text())
    assert len(records) == 1
    rec = records[0]
    assert rec["step"] == "test_step"
    assert rec["metrics"]["coverage"] == 0.97
    assert rec["inputs"][str(target)] == file_digest(target)
    assert rec["finished_at"] is not None


def test_manifest_records_errors_and_reraises(tmp_path):
    m = Manifest(tmp_path / "m.json")
    with pytest.raises(RuntimeError), m.step("failing") as rec:
        rec.metric("before", 1)
        raise RuntimeError("boom")
    assert "boom" in m.records()[0]["metrics"]["error"]


def test_end_to_end_on_synthetic_reproduces_the_predicted_ordering(tmp_path):
    """Smoke test: the full chain runs and the three-way divergence appears.

    On synthetic data calibrated to realistic wage moments, income tax should be
    more concentrated in exposed occupations than wages, and OASDI less, because
    of progressivity and the taxable maximum respectively. This asserts the
    ordering, not any particular magnitude.
    """
    paths = write_all(tmp_path, seed=1234)
    exposure = pd.read_csv(paths["exposure"])
    crosswalk = pd.read_csv(paths["crosswalk"])
    cps = pd.read_csv(paths["cps"])

    exp = exposure.rename(
        columns={"onetsoc_code": "occ_code", "observed_exposure": "exposure"}
    )[["occ_code", "exposure"]]
    cw = crosswalk.rename(
        columns={
            "onetsoc_code": "from_code",
            "cps_occ": "to_code",
            "oes_employment": "weight",
        }
    )
    cw["to_code"] = cw["to_code"].astype(str)

    mapping, report = map_exposure_to_cps(exp, cw)
    assert report.n_source_codes == len(exp)

    df = cps.rename(columns={"asecwt": "weight", "incwage": "wage", "occ": "cps_occ"})
    df["cps_occ"] = df["cps_occ"].astype(str)
    df = df[df["wage"] > 0].merge(mapping[["cps_occ", "exposure"]], on="cps_occ")
    assert len(df) > 1000

    params = TaxParams(
        year=2025,
        taxable_max=176_100.0,
        standard_deduction=15_000.0,
        brackets=[(0, 0.10), (11_925, 0.12), (48_475, 0.22), (103_350, 0.24),
                  (197_300, 0.32), (250_525, 0.35), (626_350, 0.37)],
        source="test",
    )
    df = compute_taxes(df, method="approx", params=params)
    assert (df["wage"] > params.taxable_max).sum() > 50, (
        "fixture must place some workers above the cap or the mechanism is untested"
    )

    df["group"] = assign_contrast_groups(df)
    shares = base_shares(
        df,
        group_col="group",
        value_cols={
            "Wage income": "wage",
            "Federal income tax": "iit",
            "Payroll tax (OASDI)": "oasdi",
        },
    )
    amp = amplification(shares).loc["Top quartile"]

    assert amp["Federal income tax"] > amp["Wage income"] > amp["Payroll tax (OASDI)"]
    assert np.allclose(shares.sum().to_numpy(), 1.0, atol=1e-9)
