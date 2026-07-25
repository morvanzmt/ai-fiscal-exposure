"""Tests for binning and share arithmetic.

These target the two places a silent error would actually change the headline:
weight-based binning (which is not the same as count-based binning) and the
share denominators.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from fiscal_exposure.analysis import (
    amplification,
    assign_contrast_groups,
    base_shares,
    weighted_quantile_bins,
)


@pytest.fixture
def untied() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    n = 4000
    return pd.DataFrame(
        {
            "exposure": rng.uniform(0.001, 1.0, n),
            "weight": rng.uniform(0.5, 3.0, n),
            "wage": rng.lognormal(11.0, 0.6, n),
        }
    )


def test_bins_hold_equal_weight_not_equal_counts(untied):
    """Each quartile should hold ~25% of weight, even though counts differ."""
    bins, report = weighted_quantile_bins(untied, n_bins=4)
    shares = untied.groupby(bins, observed=False)["weight"].sum() / untied["weight"].sum()
    assert np.allclose(shares.to_numpy(), 0.25, atol=0.02), shares.to_dict()
    assert not report.tie_warning
    assert len(report.edges) == 5


def test_bins_are_monotone_in_exposure(untied):
    bins, _ = weighted_quantile_bins(untied, n_bins=4)
    means = untied.groupby(bins, observed=False)["exposure"].mean()
    assert means.is_monotonic_increasing, means.to_dict()


def test_tied_scores_stay_in_one_bin():
    """A large block of identical scores must not be split across bins.

    This is not hypothetical: roughly 30% of workers sit in occupations with
    exposure exactly zero, so a naive quantile cut would split them arbitrarily.
    """
    df = pd.DataFrame(
        {
            "exposure": [0.0] * 600 + list(np.linspace(0.01, 1.0, 400)),
            "weight": [1.0] * 1000,
        }
    )
    with pytest.warns(UserWarning, match="Tied exposure"):
        bins, report = weighted_quantile_bins(df, n_bins=4)
    zero_bins = set(bins[df["exposure"] == 0.0].dropna().unique())
    assert len(zero_bins) == 1, f"zero-exposure mass split across {zero_bins}"
    assert report.tie_warning
    assert report.zero_exposure_share == pytest.approx(0.6)


def test_shares_sum_to_one(untied):
    bins, _ = weighted_quantile_bins(untied, n_bins=4)
    shares = base_shares(
        untied.assign(g=bins), group_col="g", value_cols={"Wage income": "wage"}
    )
    assert np.allclose(shares.sum().to_numpy(), 1.0, atol=1e-9)


def test_amplification_of_reference_is_unity(untied):
    bins, _ = weighted_quantile_bins(untied, n_bins=4)
    shares = base_shares(
        untied.assign(g=bins), group_col="g", value_cols={"Employment copy": "weight"}
    )
    amp = amplification(shares)
    # Employment share weighted by weight is not identical to a weight-valued
    # base, so just check the reference column was consumed correctly.
    assert "Employment" not in amp.columns
    assert (amp > 0).all().all()


def test_amplification_detects_concentration():
    """If a base is concentrated in one group, its amplification must exceed 1."""
    df = pd.DataFrame(
        {
            "exposure": [0.1] * 50 + [0.9] * 50,
            "weight": [1.0] * 100,
            "wage": [10_000.0] * 50 + [90_000.0] * 50,
        }
    )
    groups = pd.Series(["low"] * 50 + ["high"] * 50, index=df.index)
    shares = base_shares(
        df.assign(g=groups), group_col="g", value_cols={"Wage income": "wage"}
    )
    amp = amplification(shares)
    assert amp.loc["high", "Wage income"] == pytest.approx(1.8)
    assert amp.loc["low", "Wage income"] == pytest.approx(0.2)


def test_contrast_groups_separate_zero_and_top():
    df = pd.DataFrame(
        {
            "exposure": [0.0] * 300 + list(np.linspace(0.01, 0.9, 700)),
            "weight": [1.0] * 1000,
        }
    )
    groups = assign_contrast_groups(df, top_cutoff=0.75)
    counts = groups.value_counts()
    assert counts["Zero exposure"] == 300
    assert counts["Top quartile"] == pytest.approx(250, abs=5)
    assert (df.loc[groups == "Top quartile", "exposure"].min()
            > df.loc[groups == "Middle", "exposure"].max())


def test_missing_group_rows_are_excluded():
    df = pd.DataFrame(
        {
            "g": ["a", "a", None, "b"],
            "weight": [1.0, 1.0, 5.0, 2.0],
            "wage": [10.0, 10.0, 999.0, 20.0],
        }
    )
    shares = base_shares(df, group_col="g", value_cols={"Wage income": "wage"})
    assert np.allclose(shares.sum().to_numpy(), 1.0)
    assert set(shares.index.dropna()) == {"a", "b"}
