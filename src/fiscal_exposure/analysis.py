"""The core computation.

Let :math:`o` index occupations with exposure :math:`e_o`, and :math:`i` index
CPS persons with weight :math:`w_i`, occupation :math:`o(i)` and base amount
:math:`x_i` (wage income, income tax liability, payroll tax liability). For an
exposure group :math:`q`:

.. math::

    S^{x}_q = \\frac{\\sum_{i \\in q} w_i x_i}{\\sum_i w_i x_i},
    \\qquad
    S^{\\text{emp}}_q = \\frac{\\sum_{i \\in q} w_i}{\\sum_i w_i}

and the amplification factor is :math:`A^{x}_q = S^{x}_q / S^{\\text{emp}}_q`.

:math:`A^{x}_q > 1` means the base is more concentrated in exposed occupations
than headcount alone would suggest. The object of interest is not any single
:math:`A`, but the *spread* between :math:`A^{\\text{IIT}}` and
:math:`A^{\\text{OASDI}}`: progressivity concentrates income tax at the top of the
wage distribution while the Social Security taxable maximum truncates payroll
tax there. If AI exposure is concentrated at the top, the two move apart.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd

EMPLOYMENT = "employment"


@dataclass(frozen=True)
class BinReport:
    n_bins: int
    edges: list[float]
    tie_warning: bool
    zero_exposure_share: float

    def summary(self) -> str:
        msg = (
            f"{self.n_bins} bins, edges "
            f"{[round(e, 4) for e in self.edges]}; "
            f"zero-exposure employment share {self.zero_exposure_share:.1%}"
        )
        if self.tie_warning:
            msg += " [WARNING: a bin edge falls inside a block of tied scores]"
        return msg


def weighted_quantile_bins(
    df: pd.DataFrame,
    *,
    score_col: str = "exposure",
    weight_col: str = "weight",
    n_bins: int = 4,
    labels: list[str] | None = None,
) -> tuple[pd.Series, BinReport]:
    """Assign rows to bins holding roughly equal *weight*, not equal counts.

    Binning by employment rather than by occupation count is what makes "top
    quartile" mean "the most exposed quarter of workers" rather than "the most
    exposed quarter of occupation codes", which are very different objects when
    occupations differ hugely in size.

    Ties matter here. A large share of workers sit in occupations with exposure
    exactly zero, so a naive cut can split a block of identical scores across two
    bins. Ties are kept together and the resulting imbalance is reported.
    """
    work = df[[score_col, weight_col]].copy()
    work[score_col] = pd.to_numeric(work[score_col], errors="coerce")
    work[weight_col] = pd.to_numeric(work[weight_col], errors="coerce")
    valid = work.dropna()
    if valid.empty:
        raise ValueError("No valid rows to bin.")

    order = valid.sort_values(score_col, kind="mergesort")
    total = float(order[weight_col].sum())
    cum = order[weight_col].cumsum() / total

    targets = np.linspace(0, 1, n_bins + 1)[1:-1]
    raw_bins = np.searchsorted(targets, cum.to_numpy(), side="left")

    # Keep tied scores in the same bin: assign every tie block the bin of its
    # last member, then check whether that materially unbalanced the bins.
    scores = order[score_col].to_numpy()
    binned = pd.Series(raw_bins, index=order.index)
    tie_block = pd.Series(scores, index=order.index)
    binned = binned.groupby(tie_block).transform("max")

    achieved = (
        order[weight_col].groupby(binned).sum() / total
    ).reindex(range(n_bins), fill_value=0.0)
    tie_warning = bool(((achieved - 1 / n_bins).abs() > 0.5 / n_bins).any())
    if tie_warning:
        warnings.warn(
            "Tied exposure scores prevented equal-weight bins; achieved weight "
            f"shares {achieved.round(3).tolist()}. Prefer the zero-exposure vs "
            "top-quartile contrast for headline numbers.",
            stacklevel=2,
        )

    edges = [float(scores[0])]
    for b in range(n_bins - 1):
        members = scores[binned.to_numpy() == b]
        edges.append(float(members.max()) if members.size else edges[-1])
    edges.append(float(scores[-1]))

    zero_share = float(
        order.loc[order[score_col] <= 0, weight_col].sum() / total
    )

    labels = labels or [f"Q{i + 1}" for i in range(n_bins)]
    out = binned.map(dict(enumerate(labels))).reindex(df.index)
    out = pd.Series(
        pd.Categorical(out, categories=labels, ordered=True), index=df.index
    )
    return out, BinReport(n_bins, edges, tie_warning, zero_share)


def assign_contrast_groups(
    df: pd.DataFrame,
    *,
    score_col: str = "exposure",
    weight_col: str = "weight",
    top_cutoff: float = 0.75,
    zero_threshold: float = 0.0,
) -> pd.Series:
    """Anthropic's own contrast: the zero-exposure group versus the top quartile.

    Massenkoff and McCrory compare workers in the top quartile of time-weighted
    task coverage against the roughly 30% of workers whose occupations show no
    coverage. Reproducing that grouping keeps our numbers directly comparable to
    theirs, and it sidesteps the tie problem in the lower bins entirely.
    """
    score = pd.to_numeric(df[score_col], errors="coerce")
    weight = pd.to_numeric(df[weight_col], errors="coerce")
    valid = score.notna() & weight.notna()

    order = score[valid].sort_values(kind="mergesort")
    cum = weight[order.index].cumsum() / weight[valid].sum()
    above = order[cum >= top_cutoff]
    threshold = float(above.iloc[0]) if len(above) else float(order.iloc[-1])

    out = pd.Series(pd.NA, index=df.index, dtype=object)
    out[valid & (score <= zero_threshold)] = "Zero exposure"
    out[valid & (score > zero_threshold) & (score < threshold)] = "Middle"
    out[valid & (score >= threshold)] = "Top quartile"
    cats = ["Zero exposure", "Middle", "Top quartile"]
    return pd.Series(pd.Categorical(out, categories=cats, ordered=True), index=df.index)


def base_shares(
    df: pd.DataFrame,
    *,
    group_col: str,
    weight_col: str = "weight",
    value_cols: dict[str, str],
) -> pd.DataFrame:
    """Share of each base held by each exposure group.

    ``value_cols`` maps a display label to a column, e.g.
    ``{"Wage income": "wage", "Federal income tax": "iit"}``. Employment is
    always included as the reference base.
    """
    work = df.dropna(subset=[group_col]).copy()
    w = pd.to_numeric(work[weight_col], errors="coerce").fillna(0.0)

    cols: dict[str, pd.Series] = {}
    emp = w.groupby(work[group_col], observed=False).sum()
    cols["Employment"] = emp / emp.sum()

    for label, col in value_cols.items():
        if col not in work.columns:
            continue
        x = pd.to_numeric(work[col], errors="coerce").fillna(0.0)
        agg = (w * x).groupby(work[group_col], observed=False).sum()
        total = agg.sum()
        cols[label] = agg / total if total else agg * np.nan

    out = pd.DataFrame(cols)
    out.index.name = "group"
    return out


def amplification(shares: pd.DataFrame, reference: str = "Employment") -> pd.DataFrame:
    """Divide each base share by the employment share of the same group."""
    if reference not in shares.columns:
        raise KeyError(f"Reference column {reference!r} not in shares.")
    ref = shares[reference]
    out = shares.div(ref, axis=0)
    return out.drop(columns=[reference])


def cutoff_sensitivity(
    df: pd.DataFrame,
    *,
    cutoffs: list[float],
    value_cols: dict[str, str],
    score_col: str = "exposure",
    weight_col: str = "weight",
) -> pd.DataFrame:
    """Recompute the headline amplification across treatment cutoffs.

    Anthropic vary their treatment threshold from the median to the 95th
    percentile and report that conclusions are unchanged; doing the same here is
    the cheapest available guard against a result that is an artefact of one
    arbitrary cut.
    """
    rows = []
    for cut in cutoffs:
        groups = assign_contrast_groups(
            df, score_col=score_col, weight_col=weight_col, top_cutoff=cut
        )
        shares = base_shares(
            df.assign(_grp=groups),
            group_col="_grp",
            weight_col=weight_col,
            value_cols=value_cols,
        )
        amp = amplification(shares)
        if "Top quartile" in amp.index:
            row = amp.loc["Top quartile"].to_dict()
            row["cutoff"] = cut
            row["employment_share"] = float(shares.loc["Top quartile", "Employment"])
            rows.append(row)
    out = pd.DataFrame(rows)
    return out.set_index("cutoff") if not out.empty else out


def headline(shares: pd.DataFrame, group: str = "Top quartile") -> dict[str, float]:
    """The three numbers that go in the abstract."""
    if group not in shares.index:
        raise KeyError(f"Group {group!r} absent; have {list(shares.index)}")
    row = shares.loc[group]
    amp = amplification(shares).loc[group]
    return {
        "employment_share": float(row.get("Employment", np.nan)),
        "wage_share": float(row.get("Wage income", np.nan)),
        "iit_share": float(row.get("Federal income tax", np.nan)),
        "oasdi_share": float(row.get("Payroll tax (OASDI)", np.nan)),
        "amplification_wage": float(amp.get("Wage income", np.nan)),
        "amplification_iit": float(amp.get("Federal income tax", np.nan)),
        "amplification_oasdi": float(amp.get("Payroll tax (OASDI)", np.nan)),
    }
