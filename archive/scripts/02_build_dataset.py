#!/usr/bin/env python3
"""Build the analysis dataset and write the headline tables and figure.

    python scripts/02_build_dataset.py --config config/config.synthetic.yaml

Steps, each recorded in the manifest:
  1. load occupation-level exposure
  2. crosswalk it onto CPS occupation codes, weighting by OES employment
  3. join onto CPS ASEC persons and report weighted coverage
  4. compute tax liability
  5. bin by exposure, compute base shares and amplification factors
  6. write tables, figure and a machine-readable results file
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fiscal_exposure.analysis import (  # noqa: E402
    amplification,
    assign_contrast_groups,
    base_shares,
    cutoff_sensitivity,
    headline,
    weighted_quantile_bins,
)
from fiscal_exposure.config import load_config  # noqa: E402
from fiscal_exposure.cps import apply_universe, attach_exposure, load_cps  # noqa: E402
from fiscal_exposure.crosswalk import load_crosswalk, map_exposure_to_cps  # noqa: E402
from fiscal_exposure.exposure import load_exposure  # noqa: E402
from fiscal_exposure.plots import figure_main  # noqa: E402
from fiscal_exposure.provenance import Manifest  # noqa: E402
from fiscal_exposure.tax import TaxParams, compute_taxes, value_columns  # noqa: E402


def build(cfg, manifest: Manifest, *, provisional: bool) -> dict:
    with manifest.step("02_build:exposure") as rec:
        exposure = load_exposure(cfg)
        rec.metric("n_occupations", int(len(exposure)))
        rec.metric("mean_exposure", float(exposure["exposure"].mean()))

    with manifest.step("02_build:cps") as rec:
        cps_raw = load_cps(cfg)
        cps, universe_report = apply_universe(cps_raw, cfg)
        rec.metric("rows_final", universe_report["rows_final"])
        rec.metric("weighted_final", universe_report["weighted_final"])

    employment = cps.groupby("cps_occ")["weight"].sum()

    with manifest.step("02_build:crosswalk") as rec:
        crosswalk = load_crosswalk(cfg)
        mapping, coverage = map_exposure_to_cps(
            exposure,
            crosswalk,
            cps_universe=cps["cps_occ"],
            employment=employment,
        )
        rec.metric("code_coverage", coverage.code_coverage)
        rec.metric("employment_coverage", coverage.employment_covered)
        rec.metric("n_mapped_cps_codes", coverage.n_mapped_target_codes)
        print(f"  crosswalk: {coverage.summary()}")

    df = attach_exposure(cps, mapping)
    matched_weight = float(df.loc[df["exposure"].notna(), "weight"].sum())
    total_weight = float(df["weight"].sum())
    print(f"  exposure attached to {matched_weight / total_weight:.1%} of workers")

    tax_cfg = cfg.raw.get("tax", {})
    with manifest.step("02_build:tax", params=tax_cfg) as rec:
        params = TaxParams(
            year=tax_cfg.get("year", 2025),
            taxable_max=float(tax_cfg["taxable_max"]),
            standard_deduction=float(tax_cfg["standard_deduction"]),
            brackets=[tuple(b) for b in tax_cfg["brackets"]],
            source=tax_cfg.get("source", "UNSET"),
        )
        df = compute_taxes(df, method=tax_cfg.get("method", "approx"), params=params)
        rec.metric("tax_method", df["tax_method"].iloc[0])
        rec.metric("params_source", params.source)

    analysed = df.dropna(subset=["exposure"]).copy()
    vcols = value_columns(has_tax="iit" in analysed.columns)

    with manifest.step("02_build:shares") as rec:
        analysed["quartile"], bin_report = weighted_quantile_bins(
            analysed, n_bins=cfg.analysis.n_quantiles
        )
        analysed["group"] = assign_contrast_groups(
            analysed, zero_threshold=cfg.analysis.zero_exposure_threshold
        )
        print(f"  bins: {bin_report.summary()}")

        shares_contrast = base_shares(
            analysed, group_col="group", value_cols=vcols
        )
        shares_quartile = base_shares(
            analysed, group_col="quartile", value_cols=vcols
        )
        amp_contrast = amplification(shares_contrast)
        sens = cutoff_sensitivity(
            analysed, cutoffs=cfg.analysis.treatment_cutoffs, value_cols=vcols
        )
        head = headline(shares_contrast)
        for k, v in head.items():
            rec.metric(k, v)

    tables = {
        "shares_by_contrast_group": shares_contrast,
        "shares_by_quartile": shares_quartile,
        "amplification_by_contrast_group": amp_contrast,
        "cutoff_sensitivity": sens,
    }
    with manifest.step("02_build:write") as rec:
        for name, tbl in tables.items():
            if tbl is None or tbl.empty:
                continue
            path = cfg.paths.tables / f"{name}.csv"
            tbl.to_csv(path)
            rec.add_output(path)

        subtitle = (
            "SYNTHETIC DATA - machinery check only"
            if provisional
            else "Sources: Anthropic Economic Index (labor_market_impacts); "
            "CPS ASEC; EIG crosswalk"
        )
        figs = figure_main(
            shares_contrast,
            sens,
            outdir=cfg.paths.figures,
            provisional=provisional,
            subtitle=subtitle,
        )
        for f in figs:
            rec.add_output(f)

        results = {
            "provisional": provisional,
            "headline": head,
            "crosswalk_code_coverage": coverage.code_coverage,
            "crosswalk_employment_coverage": coverage.employment_covered,
            "weighted_exposure_match_rate": matched_weight / total_weight,
            "bin_report": bin_report.summary(),
            "tax_method": str(df["tax_method"].iloc[0]),
            "universe": universe_report,
        }
        rpath = cfg.paths.tables / "results.json"
        rpath.write_text(json.dumps(results, indent=2, default=str) + "\n")
        rec.add_output(rpath)

    return {"tables": tables, "results": results, "frame": analysed}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="config/config.yaml")
    args = ap.parse_args()

    cfg = load_config(args.config)
    provisional = "synthetic" in str(args.config).lower() or (
        cfg.exposure.source == "synthetic"
    )
    if provisional:
        print("\n*** SYNTHETIC RUN - numbers are meaningless ***\n")

    manifest = Manifest(cfg.paths.manifest)
    out = build(cfg, manifest, provisional=provisional)

    pd.set_option("display.float_format", lambda v: f"{v:,.4f}")
    print("\nShare of each base, by exposure group")
    print(out["tables"]["shares_by_contrast_group"].to_string())
    print("\nAmplification vs employment share")
    print(out["tables"]["amplification_by_contrast_group"].to_string())

    h = out["results"]["headline"]
    print("\n" + "=" * 66)
    print("HEADLINE (top exposure quartile)")
    print("=" * 66)
    print(f"  employment share      {h['employment_share']:.1%}")
    print(f"  wage income share     {h['wage_share']:.1%}   "
          f"(x{h['amplification_wage']:.2f})")
    if h["iit_share"] == h["iit_share"]:
        print(f"  income tax share      {h['iit_share']:.1%}   "
              f"(x{h['amplification_iit']:.2f})")
        print(f"  OASDI payroll share   {h['oasdi_share']:.1%}   "
              f"(x{h['amplification_oasdi']:.2f})")
        spread = h["amplification_iit"] - h["amplification_oasdi"]
        print(f"\n  IIT-OASDI amplification spread: {spread:+.2f}")
    print("=" * 66 + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
