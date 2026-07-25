"""Tests for tax computation.

The payroll cap test is the important one. The entire fiscal argument rests on
OASDI liability flattening above the taxable maximum while income tax keeps
rising, so if that property broke silently the headline result would be wrong in
a way no amount of eyeballing the figure would catch.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from fiscal_exposure.tax import TaxParams, income_tax_approx, payroll_tax

PARAMS = TaxParams(
    year=2025,
    taxable_max=176_100.0,
    standard_deduction=15_000.0,
    brackets=[
        (0, 0.10),
        (11_925, 0.12),
        (48_475, 0.22),
        (103_350, 0.24),
        (197_300, 0.32),
        (250_525, 0.35),
        (626_350, 0.37),
    ],
    source="test fixture",
)


def test_oasdi_is_capped_at_taxable_max():
    wage = pd.Series([50_000, PARAMS.taxable_max, 400_000, 2_000_000], dtype=float)
    out = payroll_tax(wage, PARAMS)
    ceiling = PARAMS.taxable_max * PARAMS.oasdi_rate
    assert out.loc[0, "oasdi"] == pytest.approx(50_000 * PARAMS.oasdi_rate)
    assert out.loc[1, "oasdi"] == pytest.approx(ceiling)
    assert out.loc[2, "oasdi"] == pytest.approx(ceiling)
    assert out.loc[3, "oasdi"] == pytest.approx(ceiling)


def test_hi_is_uncapped():
    wage = pd.Series([100_000, 1_000_000], dtype=float)
    out = payroll_tax(wage, PARAMS)
    assert out.loc[1, "hi"] == pytest.approx(10 * out.loc[0, "hi"])


def test_effective_oasdi_rate_falls_above_the_cap():
    """The mechanism, stated as a test.

    Below the cap the average OASDI rate is flat; above it, it declines. This is
    what compresses payroll-tax concentration at the top of the wage
    distribution, which is exactly where AI exposure sits.
    """
    wage = pd.Series([80_000, 150_000, 300_000, 600_000], dtype=float)
    out = payroll_tax(wage, PARAMS)
    eff = out["oasdi"] / wage
    assert eff.iloc[0] == pytest.approx(PARAMS.oasdi_rate)
    assert eff.iloc[1] == pytest.approx(PARAMS.oasdi_rate)
    assert eff.iloc[2] < eff.iloc[1]
    assert eff.iloc[3] < eff.iloc[2]


def test_income_tax_average_rate_is_increasing():
    """Progressivity: the average income tax rate rises with wage."""
    wage = pd.Series([30_000, 60_000, 120_000, 300_000, 900_000], dtype=float)
    eff = income_tax_approx(wage, PARAMS) / wage
    assert np.all(np.diff(eff.to_numpy()) > 0), eff.to_dict()


def test_income_tax_zero_below_standard_deduction():
    wage = pd.Series([0.0, 5_000.0, PARAMS.standard_deduction], dtype=float)
    assert (income_tax_approx(wage, PARAMS) == 0).all()


def test_bracket_arithmetic_matches_hand_calculation():
    """A single hand-checked value guards against off-by-one bracket errors."""
    wage = pd.Series([50_000.0])
    # taxable = 50,000 - 15,000 standard deduction = 35,000
    expected = 11_925 * 0.10 + (35_000 - 11_925) * 0.12
    assert income_tax_approx(wage, PARAMS).iloc[0] == pytest.approx(expected)


def test_params_validation_rejects_unsorted_brackets():
    bad = TaxParams(
        year=2025,
        taxable_max=1.0,
        standard_deduction=0.0,
        brackets=[(0, 0.1), (100, 0.2), (50, 0.3)],
    )
    with pytest.raises(ValueError, match="ascending"):
        bad.validate()


def test_params_validation_rejects_empty_brackets():
    with pytest.raises(ValueError, match="No brackets"):
        TaxParams(year=2025, taxable_max=1.0, standard_deduction=0.0).validate()
