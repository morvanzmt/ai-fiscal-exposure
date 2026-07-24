"""Federal tax liability.

Two paths, and the choice is reported in the output rather than buried.

``taxsim``
    NBER TAXSIM 35 (https://taxsim.nber.org/), which returns federal income tax
    and FICA separately. This is the path to use for anything published.

``approx``
    A transparent closed-form approximation using statutory brackets and the
    Social Security taxable maximum. It exists so the pipeline runs end to end
    without network access, and so the *mechanism* behind the payroll result is
    legible in code. It is not a substitute for TAXSIM and is labelled as such
    everywhere it is used.

The payroll result does not depend on fine calibration. Above the contribution
and benefit base (2025: $176,100, see https://www.ssa.gov/oact/cola/cbb.html)
the OASDI rate falls to zero at the margin while income tax rates keep rising.
Any method that respects the cap reproduces the divergence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

OASDI_RATE_EMPLOYEE = 0.062
HI_RATE_EMPLOYEE = 0.0145


@dataclass(frozen=True)
class TaxParams:
    """Statutory parameters for the approximation path.

    Defaults are placeholders and must be set from a cited source before any
    published run; ``source`` records where they came from.
    """

    year: int
    taxable_max: float
    standard_deduction: float
    brackets: list[tuple[float, float]] = field(default_factory=list)
    oasdi_rate: float = OASDI_RATE_EMPLOYEE
    hi_rate: float = HI_RATE_EMPLOYEE
    source: str = "UNSET - populate from IRS Rev. Proc. and SSA before publishing"

    def validate(self) -> None:
        if not self.brackets:
            raise ValueError("No brackets configured.")
        thresholds = [t for t, _ in self.brackets]
        if thresholds != sorted(thresholds):
            raise ValueError("Bracket thresholds must be ascending.")
        if thresholds[0] != 0:
            raise ValueError("First bracket must start at 0.")
        if self.taxable_max <= 0:
            raise ValueError("taxable_max must be positive.")


def payroll_tax(wage: pd.Series, params: TaxParams) -> pd.DataFrame:
    """Employee-side OASDI and HI liability.

    OASDI applies only up to the taxable maximum. HI is uncapped. Splitting them
    is the point: they behave in opposite ways at the top of the wage
    distribution, which is exactly where AI exposure is concentrated.
    """
    w = pd.to_numeric(wage, errors="coerce").fillna(0.0).clip(lower=0)
    oasdi = np.minimum(w, params.taxable_max) * params.oasdi_rate
    hi = w * params.hi_rate
    return pd.DataFrame(
        {"oasdi": oasdi, "hi": hi, "payroll_total": oasdi + hi}, index=wage.index
    )


def income_tax_approx(wage: pd.Series, params: TaxParams) -> pd.Series:
    """Piecewise-linear statutory income tax on wage income alone.

    Deliberately crude: single filer, no dependants, no credits, no non-wage
    income, no itemising. It will misstate levels. It preserves progressivity,
    which is the only property the amplification result depends on.
    """
    params.validate()
    taxable = (
        pd.to_numeric(wage, errors="coerce").fillna(0.0) - params.standard_deduction
    ).clip(lower=0)

    liability = pd.Series(0.0, index=wage.index)
    for idx, (lower, rate) in enumerate(params.brackets):
        upper = (
            params.brackets[idx + 1][0]
            if idx + 1 < len(params.brackets)
            else np.inf
        )
        in_band = (taxable.clip(upper=upper) - lower).clip(lower=0)
        liability += in_band * rate
    return liability


def compute_taxes(
    df: pd.DataFrame,
    *,
    method: str = "approx",
    params: TaxParams | None = None,
    wage_col: str = "wage",
) -> pd.DataFrame:
    """Attach ``iit``, ``oasdi``, ``hi`` and ``tax_method`` columns."""
    out = df.copy()
    if method == "approx":
        if params is None:
            raise ValueError("TaxParams required for the approximation path.")
        out["iit"] = income_tax_approx(out[wage_col], params)
        payroll = payroll_tax(out[wage_col], params)
        out[["oasdi", "hi", "payroll_total"]] = payroll
        out["tax_method"] = f"approx:{params.year}"
    elif method == "taxsim":
        raise NotImplementedError(
            "TAXSIM path: build the input file per https://taxsim.nber.org/taxsim35/ "
            "and populate iit/oasdi/hi from the returned columns. Wire this once "
            "the CPS extract has the household variables (marital status, "
            "dependants, state, non-wage income)."
        )
    else:
        raise ValueError(f"Unknown tax method {method!r}.")
    return out


def value_columns(has_tax: bool) -> dict[str, str]:
    """Standard label to column mapping for the shares table."""
    cols = {"Wage income": "wage"}
    if has_tax:
        cols["Federal income tax"] = "iit"
        cols["Payroll tax (OASDI)"] = "oasdi"
    return cols
