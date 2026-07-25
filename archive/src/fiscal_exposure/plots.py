"""Figures.

Panel A is the argument: four bars for the top exposure quartile, showing its
share of employment, wages, income tax and payroll tax, with a reference line at
the employment share. Panels B and C establish that the pattern is monotone and
not an artefact of the cut.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

INK = "#1a1a1a"
MUTED = "#8a8a8a"
GRID = "#e2e2e2"
SERIES = {
    "Employment": "#9aa5b1",
    "Wage income": "#4c78a8",
    "Federal income tax": "#b4451f",
    "Payroll tax (OASDI)": "#3d8a6b",
}


def use_style() -> None:
    mpl.rcParams.update(
        {
            "figure.dpi": 140,
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.titleweight": "semibold",
            "axes.labelsize": 10,
            "axes.edgecolor": MUTED,
            "axes.linewidth": 0.8,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": GRID,
            "grid.linewidth": 0.7,
            "xtick.color": INK,
            "ytick.color": INK,
            "text.color": INK,
            "legend.frameon": False,
        }
    )


def _pct(ax: plt.Axes, axis: str = "y") -> None:
    fmt = mpl.ticker.FuncFormatter(lambda v, _: f"{v:.0%}")
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(fmt)


def panel_a_headline(
    shares: pd.DataFrame,
    *,
    group: str = "Top quartile",
    ax: plt.Axes | None = None,
    provisional: bool = False,
) -> plt.Axes:
    """Share of each base held by the most exposed group."""
    if ax is None:
        _, ax = plt.subplots(figsize=(6.2, 4.0))
    row = shares.loc[group].dropna()
    labels = list(row.index)
    values = row.to_numpy(dtype=float)
    colors = [SERIES.get(lbl, MUTED) for lbl in labels]

    bars = ax.bar(range(len(values)), values, color=colors, width=0.62)
    emp = float(row.get("Employment", np.nan))
    if np.isfinite(emp):
        ax.axhline(emp, color=INK, lw=1.0, ls=(0, (4, 3)), zorder=3)
        ax.text(
            len(values) - 0.4,
            emp,
            "  employment share",
            va="center",
            ha="left",
            fontsize=8.5,
            color=INK,
        )

    for bar, val in zip(bars, values, strict=True):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            val,
            f"{val:.1%}",
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="semibold",
        )

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels([lbl.replace(" (", "\n(") for lbl in labels], fontsize=9)
    ax.set_ylabel("Share of national total")
    ax.set_ylim(0, max(values.max() * 1.22, emp * 1.3 if np.isfinite(emp) else 0))
    ax.set_title(f"What the {group.lower()} of AI exposure holds")
    _pct(ax)
    if provisional:
        _watermark(ax)
    return ax


def panel_b_gradient(
    shares: pd.DataFrame, *, ax: plt.Axes | None = None, provisional: bool = False
) -> plt.Axes:
    """The same series across all exposure groups."""
    if ax is None:
        _, ax = plt.subplots(figsize=(7.2, 4.0))
    groups = list(shares.index)
    labels = [c for c in shares.columns if shares[c].notna().any()]
    x = np.arange(len(groups))
    width = 0.8 / max(len(labels), 1)

    for k, lbl in enumerate(labels):
        ax.bar(
            x + k * width - 0.4 + width / 2,
            shares[lbl].to_numpy(dtype=float),
            width=width,
            label=lbl,
            color=SERIES.get(lbl, MUTED),
        )

    ax.set_xticks(x)
    ax.set_xticklabels(groups)
    ax.set_ylabel("Share of national total")
    ax.set_xlabel("AI exposure group")
    ax.set_title("Base composition across the exposure gradient")
    ax.legend(ncol=2, fontsize=8.5, loc="upper left")
    _pct(ax)
    if provisional:
        _watermark(ax)
    return ax


def panel_c_sensitivity(
    sens: pd.DataFrame, *, ax: plt.Axes | None = None, provisional: bool = False
) -> plt.Axes:
    """Amplification factors as the treatment cutoff moves."""
    if ax is None:
        _, ax = plt.subplots(figsize=(6.2, 4.0))
    for lbl in sens.columns:
        if lbl == "employment_share":
            continue
        ax.plot(
            sens.index,
            sens[lbl],
            marker="o",
            ms=4.5,
            lw=1.6,
            label=lbl,
            color=SERIES.get(lbl, MUTED),
        )
    ax.axhline(1.0, color=INK, lw=1.0, ls=(0, (4, 3)))
    ax.set_xlabel("Treatment cutoff (weighted percentile of exposure)")
    ax.set_ylabel("Amplification vs employment share")
    ax.set_title("Robustness to the treatment cutoff")
    ax.legend(fontsize=8.5)
    _pct(ax, axis="x")
    if provisional:
        _watermark(ax)
    return ax


def _watermark(ax: plt.Axes) -> None:
    ax.text(
        0.5,
        0.5,
        "SYNTHETIC DATA",
        transform=ax.transAxes,
        fontsize=26,
        color="#d02020",
        alpha=0.16,
        ha="center",
        va="center",
        rotation=24,
        fontweight="bold",
        zorder=10,
    )


def figure_main(
    shares: pd.DataFrame,
    sens: pd.DataFrame | None,
    *,
    outdir: str | Path,
    stem: str = "fig1_fiscal_exposure",
    provisional: bool = False,
    subtitle: str | None = None,
) -> list[Path]:
    """Render and save the composite figure. Returns the paths written."""
    use_style()
    n = 3 if sens is not None and not sens.empty else 2
    fig, axes = plt.subplots(1, n, figsize=(5.6 * n, 4.2))
    panel_a_headline(shares, ax=axes[0], provisional=provisional)
    panel_b_gradient(shares, ax=axes[1], provisional=provisional)
    if n == 3:
        panel_c_sensitivity(sens, ax=axes[2], provisional=provisional)

    if subtitle:
        fig.text(0.5, -0.02, subtitle, ha="center", fontsize=8.5, color=MUTED)
    fig.tight_layout()

    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    written = []
    for ext in ("png", "pdf"):
        path = outdir / f"{stem}.{ext}"
        fig.savefig(path)
        written.append(path)
    plt.close(fig)
    return written
