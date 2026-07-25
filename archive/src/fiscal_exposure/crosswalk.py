"""Occupation crosswalk: O*NET-SOC to CPS occupation codes.

O*NET-SOC is finer than the occupation coding on CPS microdata, so the mapping is
many-to-one and the aggregation rule matters. Where several O*NET-SOC codes map
to one CPS code we take an employment-weighted mean of exposure, using BLS OES
employment as weights; an unweighted mean is retained as a robustness variant.

We use the crosswalk of Eckhardt and Goldschlag (2025, Economic Innovation
Group), which is the same one used by Massenkoff and McCrory (2026). Holding the
occupation mapping identical to theirs means any divergence in results is
attributable to the fiscal layer rather than to plumbing.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from fiscal_exposure.config import Config
from fiscal_exposure.exposure import read_any


@dataclass(frozen=True)
class CoverageReport:
    """How much of the target universe actually received an exposure score."""

    n_source_codes: int
    n_target_codes: int
    n_mapped_target_codes: int
    employment_covered: float | None
    unmapped_examples: list[str]

    @property
    def code_coverage(self) -> float:
        if self.n_target_codes == 0:
            return 0.0
        return self.n_mapped_target_codes / self.n_target_codes

    def summary(self) -> str:
        emp = (
            f"{self.employment_covered:.1%}"
            if self.employment_covered is not None
            else "n/a"
        )
        return (
            f"{self.n_mapped_target_codes}/{self.n_target_codes} target codes "
            f"mapped ({self.code_coverage:.1%}); employment covered {emp}"
        )


def soc6_from_onet(codes: pd.Series) -> pd.Series:
    """Reduce O*NET-SOC 8-digit codes to their 6-digit SOC parent.

    ``15-1251.00`` -> ``15-1251``. Values that are already 6-digit pass through.
    """
    return codes.astype(str).str.strip().str.split(".").str[0]


def load_crosswalk(cfg: Config) -> pd.DataFrame:
    """Load the crosswalk, normalised to ``[from_code, to_code, weight]``."""
    matches = sorted(cfg.paths.raw.glob(cfg.crosswalk.file_glob))
    if not matches:
        raise FileNotFoundError(
            f"No crosswalk matching {cfg.crosswalk.file_glob!r} under "
            f"{cfg.paths.raw}. See data/README.md for retrieval instructions."
        )
    df = read_any(matches[0])
    cw = cfg.crosswalk

    missing = [c for c in (cw.from_col, cw.to_col) if c not in df.columns]
    if missing:
        raise KeyError(
            f"Crosswalk columns {missing} absent. Available: {list(df.columns)}"
        )

    cols = {cw.from_col: "from_code", cw.to_col: "to_code"}
    if cw.weight_col and cw.weight_col in df.columns:
        cols[cw.weight_col] = "weight"
    out = df[list(cols)].rename(columns=cols)

    out["from_code"] = out["from_code"].astype(str).str.strip()
    out["to_code"] = out["to_code"].astype(str).str.strip()
    if "weight" not in out.columns:
        out["weight"] = 1.0
    out["weight"] = pd.to_numeric(out["weight"], errors="coerce").fillna(0.0)
    # A zero-weight group would collapse to NaN; fall back to equal weights.
    out.loc[out.groupby("to_code")["weight"].transform("sum") <= 0, "weight"] = 1.0

    return out.dropna(subset=["from_code", "to_code"]).reset_index(drop=True)


def map_exposure_to_cps(
    exposure: pd.DataFrame,
    crosswalk: pd.DataFrame,
    *,
    cps_universe: pd.Series | None = None,
    employment: pd.Series | None = None,
) -> tuple[pd.DataFrame, CoverageReport]:
    """Aggregate O*NET-SOC exposure onto CPS occupation codes.

    Parameters
    ----------
    exposure
        ``[occ_code, exposure]`` from :func:`fiscal_exposure.exposure.load_exposure`.
    crosswalk
        ``[from_code, to_code, weight]`` from :func:`load_crosswalk`.
    cps_universe
        Optional set of CPS occupation codes that exist in the microdata, used to
        report coverage honestly rather than only over codes we happened to map.
    employment
        Optional employment by CPS occupation code, used to report the share of
        *workers* covered rather than the share of *codes*.

    Returns
    -------
    (mapping, report)
        ``mapping`` has ``[cps_occ, exposure, exposure_unweighted, n_source_codes]``.
    """
    merged = crosswalk.merge(
        exposure, left_on="from_code", right_on="occ_code", how="inner"
    )
    if merged.empty:
        raise ValueError(
            "Crosswalk and exposure share no codes. Check that "
            "exposure.occ_code_kind matches crosswalk.from_col coding."
        )

    def _wmean(g: pd.DataFrame) -> float:
        w = g["weight"].to_numpy(dtype=float)
        x = g["exposure"].to_numpy(dtype=float)
        return float(np.average(x, weights=w)) if w.sum() > 0 else float(x.mean())

    grouped = merged.groupby("to_code")
    mapping = pd.DataFrame(
        {
            "exposure": grouped.apply(_wmean, include_groups=False),
            "exposure_unweighted": grouped["exposure"].mean(),
            "n_source_codes": grouped["from_code"].nunique(),
        }
    ).reset_index(names="cps_occ")

    if cps_universe is not None:
        universe = pd.Index(cps_universe.astype(str).str.strip().unique())
    else:
        universe = pd.Index(mapping["cps_occ"].unique())

    mapped = pd.Index(mapping["cps_occ"].unique())
    unmapped = universe.difference(mapped)

    emp_covered = None
    if employment is not None:
        emp = employment.copy()
        emp.index = emp.index.astype(str).str.strip()
        total = float(emp.sum())
        if total > 0:
            emp_covered = float(emp.reindex(mapped).fillna(0).sum() / total)

    report = CoverageReport(
        n_source_codes=int(exposure["occ_code"].nunique()),
        n_target_codes=int(len(universe)),
        n_mapped_target_codes=int(len(universe.intersection(mapped))),
        employment_covered=emp_covered,
        unmapped_examples=[str(c) for c in unmapped[:20]],
    )
    return mapping, report
