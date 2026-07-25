#!/usr/bin/env python3
"""Generate notebooks/walkthrough.ipynb.

The notebook is built from source so it stays in sync with the package and so
diffs stay reviewable. Run after changing the narrative.
"""

from __future__ import annotations

from pathlib import Path

import nbformat as nbf

MD = nbf.v4.new_markdown_cell
CODE = nbf.v4.new_code_cell

CELLS = [
    MD(
        """# Employment exposure is not fiscal exposure

**How much of the US federal tax base sits in AI-exposed occupations, and how does that differ from how much of the workforce does?**

Every existing measure of AI exposure is employment-weighted: it asks what share of *workers* sit in exposed occupations. Fiscal capacity is not distributed like headcount. Under a progressive income tax, revenue is far more concentrated than employment. And above the Social Security taxable maximum, payroll tax stops accruing entirely.

Massenkoff and McCrory (2026) report that workers in the most exposed occupations earn roughly 47% more than the unexposed and are nearly four times as likely to hold a graduate degree. If exposure really is concentrated at the top of the earnings distribution, three consequences follow that nobody has measured:

1. The **wage base** in exposed occupations exceeds their employment share.
2. The **income tax base** exceeds even that, because progressivity compounds the earnings gap.
3. The **payroll tax base** does not, because the taxable maximum truncates liability exactly where exposure concentrates.

The spread between (2) and (3) is the result. It would mean AI exposure threatens the revenue funding general government rather than the revenue funding social insurance, which inverts the robot era, when displacement sat in the middle of the wage distribution.

---

> **This notebook currently runs on synthetic fixtures.** Numbers are meaningless and figures are watermarked. Swap the config once the CPS extract clears."""
    ),
    CODE(
        """import sys
from pathlib import Path

ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from fiscal_exposure.analysis import (
    amplification, assign_contrast_groups, base_shares,
    cutoff_sensitivity, headline, weighted_quantile_bins,
)
from fiscal_exposure.config import load_config
from fiscal_exposure.cps import apply_universe, attach_exposure, load_cps
from fiscal_exposure.crosswalk import load_crosswalk, map_exposure_to_cps
from fiscal_exposure.exposure import load_exposure
from fiscal_exposure.plots import panel_a_headline, panel_b_gradient, panel_c_sensitivity, use_style
from fiscal_exposure.synthetic import write_all
from fiscal_exposure.tax import TaxParams, compute_taxes, value_columns

use_style()
pd.set_option("display.float_format", lambda v: f"{v:,.4f}")

CONFIG = ROOT / "config" / "config.synthetic.yaml"   # <- swap for config.yaml
PROVISIONAL = "synthetic" in CONFIG.name
print("config:", CONFIG.name, "| provisional:", PROVISIONAL)"""
    ),
    MD(
        """## 1. Inputs

Three ingredients. Occupation-level exposure from the Anthropic Economic Index, a crosswalk from O\\*NET-SOC onto CPS occupation codes, and CPS ASEC person records carrying earnings and weights.

If you are on synthetic data, generate the fixtures first."""
    ),
    CODE(
        """cfg = load_config(CONFIG)

if PROVISIONAL:
    write_all(cfg.paths.raw, seed=cfg.analysis.seed)

exposure = load_exposure(cfg)
print(f"{len(exposure):,} occupations with an exposure score")
exposure.describe().T"""
    ),
    MD(
        """Note the mass at zero. Anthropic report that around 30% of workers sit in occupations whose tasks appeared too rarely in their data to clear the coverage threshold. That tie block matters for binning later, and the code handles it explicitly rather than letting a quantile cut split it arbitrarily."""
    ),
    CODE(
        """ax = exposure["exposure"].plot.hist(bins=40, color="#4c78a8", figsize=(6.4, 3.4))
ax.set_xlabel("Observed exposure")
ax.set_ylabel("Occupations")
ax.set_title("Distribution of exposure across occupations")
share_zero = (exposure["exposure"] <= 0).mean()
print(f"{share_zero:.1%} of occupation codes have zero exposure")"""
    ),
    MD(
        """## 2. Crosswalk

O\\*NET-SOC is finer than CPS occupation coding, so the mapping is many-to-one and the aggregation rule matters. Where several O\\*NET codes collapse into one CPS code we take an **employment-weighted** mean, using BLS OES employment. A simple mean would weight a tiny occupation the same as a huge one, which would bias exposure for exactly the large categories carrying most of the tax base.

We use the Eckhardt and Goldschlag (2025) crosswalk, the same one Massenkoff and McCrory used. Holding the occupation mapping identical to theirs means any divergence in results is attributable to the fiscal layer rather than to plumbing.

Coverage is reported two ways, because they differ a lot: the share of occupation *codes* mapped, and the share of *workers* covered."""
    ),
    CODE(
        """cps_raw = load_cps(cfg)
cps, universe = apply_universe(cps_raw, cfg)
employment = cps.groupby("cps_occ")["weight"].sum()

crosswalk = load_crosswalk(cfg)
mapping, coverage = map_exposure_to_cps(
    exposure, crosswalk, cps_universe=cps["cps_occ"], employment=employment
)
print(coverage.summary())
if coverage.unmapped_examples:
    print("unmapped examples:", coverage.unmapped_examples[:8])"""
    ),
    CODE(
        """df = attach_exposure(cps, mapping)
matched = df["exposure"].notna()
print(f"exposure attached to {df.loc[matched, 'weight'].sum() / df['weight'].sum():.1%} of workers")
print(f"universe: {universe['rows_final']:,} persons, "
      f"{universe['weighted_final']:,.0f} weighted")"""
    ),
    MD(
        """## 3. Tax liability

The approximation path applies statutory brackets and the Social Security taxable maximum. It is deliberately crude, and it is not what a published run should use: single filer, no dependants, no credits, wage income only. It exists so the pipeline runs offline and so the mechanism is legible in code.

The result does not depend on fine calibration. Above the contribution and benefit base the marginal OASDI rate is zero while income tax rates keep rising. Any method respecting the cap reproduces the divergence. For publication, switch `tax.method` to `taxsim`.

**The parameters shipped in config are placeholders.** Replace them with cited values from the relevant IRS Revenue Procedure and the SSA base table before publishing."""
    ),
    CODE(
        """tax_cfg = cfg.raw["tax"]
params = TaxParams(
    year=tax_cfg["year"],
    taxable_max=float(tax_cfg["taxable_max"]),
    standard_deduction=float(tax_cfg["standard_deduction"]),
    brackets=[tuple(b) for b in tax_cfg["brackets"]],
    source=tax_cfg["source"],
)
print("parameter source:", params.source)

df = compute_taxes(df, method=tax_cfg["method"], params=params)
above_cap = (df["wage"] > params.taxable_max)
print(f"{df.loc[above_cap, 'weight'].sum() / df['weight'].sum():.1%} of workers "
      f"earn above the taxable maximum (${params.taxable_max:,.0f})")"""
    ),
    MD(
        """The mechanism, made visible: average OASDI rate against wage. It is flat up to the cap, then falls. Income tax does the opposite."""
    ),
    CODE(
        """import matplotlib.pyplot as plt

sample = df[df["wage"] > 0].sample(min(6000, len(df)), random_state=0).sort_values("wage")
fig, ax = plt.subplots(figsize=(6.6, 3.6))
ax.plot(sample["wage"], sample["oasdi"] / sample["wage"], lw=1.8,
        color="#3d8a6b", label="OASDI payroll")
ax.plot(sample["wage"], sample["iit"] / sample["wage"], lw=1.8,
        color="#b4451f", label="Federal income tax")
ax.axvline(params.taxable_max, color="#1a1a1a", ls=(0, (4, 3)), lw=1.0)
ax.text(params.taxable_max, ax.get_ylim()[1] * 0.92, "  taxable max", fontsize=8.5)
ax.set_xscale("log"); ax.set_xlabel("Wage income (log scale)")
ax.set_ylabel("Average rate"); ax.legend()
ax.set_title("Why the two bases diverge at the top")
plt.show()"""
    ),
    MD(
        """## 4. Binning

"Top quartile" should mean the most exposed quarter of *workers*, not the most exposed quarter of *occupation codes*. Occupations differ enormously in size, so those are different objects. Bins are cut on cumulative employment weight.

Ties are the complication. With a large block of workers at exactly zero exposure, a naive cut splits identical scores across bins. The code keeps ties together and warns when that unbalances the bins, which is why the headline uses Anthropic's own contrast (zero-exposure group versus top quartile) rather than raw quartiles."""
    ),
    CODE(
        """analysed = df.dropna(subset=["exposure"]).copy()

analysed["quartile"], bin_report = weighted_quantile_bins(
    analysed, n_bins=cfg.analysis.n_quantiles
)
analysed["group"] = assign_contrast_groups(
    analysed, zero_threshold=cfg.analysis.zero_exposure_threshold
)
print(bin_report.summary())
analysed.groupby("group", observed=False).agg(
    workers=("weight", "sum"),
    mean_exposure=("exposure", "mean"),
    mean_wage=("wage", "mean"),
)"""
    ),
    MD(
        """Check the earnings gradient against the published figure. Massenkoff and McCrory report the top-quartile group earns about 47% more than the unexposed group. If our number is far off, the crosswalk or the universe filter is wrong."""
    ),
    CODE(
        """by_group = analysed.groupby("group", observed=False).apply(
    lambda g: (g["wage"] * g["weight"]).sum() / g["weight"].sum(), include_groups=False
)
gap = by_group["Top quartile"] / by_group["Zero exposure"] - 1
print(f"mean wage gap, top quartile vs zero exposure: {gap:+.1%}")
print("(Massenkoff & McCrory report roughly +47% on real data)")"""
    ),
    MD(
        """## 5. The result

Share of each base held by each exposure group, then the amplification factor: each base share divided by the same group's employment share.

$$S^{x}_q = \\frac{\\sum_{i \\in q} w_i x_i}{\\sum_i w_i x_i}, \\qquad A^{x}_q = \\frac{S^{x}_q}{S^{\\text{emp}}_q}$$

$A > 1$ means the base is more concentrated in exposed occupations than headcount alone implies."""
    ),
    CODE(
        """vcols = value_columns(has_tax=True)
shares = base_shares(analysed, group_col="group", value_cols=vcols)
shares"""
    ),
    CODE(
        """amp = amplification(shares)
amp"""
    ),
    CODE(
        """h = headline(shares)
print(f"  employment share      {h['employment_share']:.1%}")
print(f"  wage income share     {h['wage_share']:.1%}   (x{h['amplification_wage']:.2f})")
print(f"  income tax share      {h['iit_share']:.1%}   (x{h['amplification_iit']:.2f})")
print(f"  OASDI payroll share   {h['oasdi_share']:.1%}   (x{h['amplification_oasdi']:.2f})")
print(f"\\n  IIT minus OASDI amplification: "
      f"{h['amplification_iit'] - h['amplification_oasdi']:+.2f}")"""
    ),
    MD(
        """## 6. Robustness

The quartile cut is arbitrary. Anthropic vary their treatment threshold from the median to the 95th percentile and report conclusions unchanged; the same check here is the cheapest guard against a result that is an artefact of one cut."""
    ),
    CODE(
        """sens = cutoff_sensitivity(
    analysed, cutoffs=cfg.analysis.treatment_cutoffs, value_cols=vcols
)
sens"""
    ),
    CODE(
        """fig, axes = plt.subplots(1, 3, figsize=(16.8, 4.2))
panel_a_headline(shares, ax=axes[0], provisional=PROVISIONAL)
panel_b_gradient(shares, ax=axes[1], provisional=PROVISIONAL)
panel_c_sensitivity(sens, ax=axes[2], provisional=PROVISIONAL)
fig.tight_layout()
plt.show()"""
    ),
    MD(
        """## 7. What this is and is not

A static accounting of the composition of **today's** tax base. Not a forecast, not a displacement estimate. It measures how much of the base sits in the line of fire, not how much will be lost.

- Exposure is measured from **Claude usage**, not all AI usage.
- **Exposure is not displacement.** Anthropic find no systematic unemployment increase among exposed workers so far, with only tentative evidence of slowed hiring for workers aged 22 to 25.
- The theoretical-capability layer is pinned to early-2023 LLM capability.
- CPS occupation is self-reported; wage income is top-coded, which biases the headline **downward**. The result is conservative.
- No behavioural response, no reallocation, no general equilibrium. Displaced workers move to other occupations in reality, and that is exactly the mechanism which rescued the tax base in the robot era. Whether it recurs is the open question.
- Tax is levied on units, not persons; two-earner couples split across exposure groups are approximated here.

ITIF argue the erosion concern is overstated, since labour's share would have to fall dramatically and persistently and displaced workers historically transition rather than disappear. Nothing here refutes that. What it changes is *which* revenue stream is at risk, which matters either way.

## 8. Next

The Budget Lab at Yale names the missing input for its AI tax microsimulation: an occupation-level exposure imputation onto the tax-unit file, absent because the IRS Public Use File carries no occupation. CPS does, which is why this pilot starts here. Doing the statistical match onto the PUF properly is the obvious next step, followed by extension across OECD tax mixes, where the same exposure shock has very different fiscal consequences depending on whether a country finances social protection through payroll contributions or through VAT."""
    ),
]


def main() -> int:
    nb = nbf.v4.new_notebook(cells=CELLS)
    nb.metadata = {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {"name": "python", "version": "3.11"},
    }
    out = Path(__file__).resolve().parent.parent / "notebooks" / "walkthrough.ipynb"
    out.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(nb, out)
    print(f"wrote {out} ({len(CELLS)} cells)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
