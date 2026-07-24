"""Synthetic fixtures.

Generates structurally realistic stand-ins for the three inputs so that the
pipeline, the tests and the notebook all run end to end before any download has
completed. The numbers it produces are meaningless. Every figure drawn from it
carries a SYNTHETIC DATA watermark and every artefact is written under a
``synthetic_`` prefix.

Two stylised facts from Massenkoff and McCrory (2026) are baked in, so that the
machinery is exercised on data shaped like the real thing: roughly 30% of
workers sit in occupations with zero observed coverage, and workers in the top
exposure quartile earn substantially more than the unexposed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

N_OCC = 420
N_PERSONS = 60_000
ZERO_EXPOSURE_OCC_SHARE = 0.34

# Calibrated so the fixture exercises the mechanism rather than flattering it.
# LOG_WAGE_MU/SIGMA are set near published US wage-and-salary moments (median
# around $60k, right-skewed) so that a realistic slice of the top exposure group
# sits ABOVE the Social Security taxable maximum. If wages are too low the cap
# never binds and the payroll result cannot appear, which would make the
# machinery untestable. EARNINGS_GRADIENT is set so the mean wage gap between
# the top-quartile and zero-exposure groups lands near the ~47% reported by
# Massenkoff and McCrory (2026).
LOG_WAGE_MU = 10.93
LOG_WAGE_SIGMA = 0.66
EARNINGS_GRADIENT = 0.75  # log-wage gain from zero to full exposure


def _onet_codes(rng: np.random.Generator, n: int) -> list[str]:
    majors = [11, 13, 15, 17, 19, 21, 23, 25, 27, 29, 31, 33, 35, 37, 39, 41, 43,
              45, 47, 49, 51, 53]
    seen: set[str] = set()
    out: list[str] = []
    while len(out) < n:
        code = (
            f"{rng.choice(majors):02d}-{rng.integers(1000, 9999):04d}"
            f".{rng.choice([0, 1, 2]):02d}"
        )
        if code not in seen:
            seen.add(code)
            out.append(code)
    return out


def make_exposure(rng: np.random.Generator) -> pd.DataFrame:
    codes = _onet_codes(rng, N_OCC)
    n_zero = int(N_OCC * ZERO_EXPOSURE_OCC_SHARE)
    scores = np.concatenate(
        [np.zeros(n_zero), rng.beta(1.7, 3.0, N_OCC - n_zero)]
    )
    rng.shuffle(scores)
    return pd.DataFrame(
        {
            "onetsoc_code": codes,
            "occupation_title": [f"Synthetic occupation {i:04d}" for i in range(N_OCC)],
            "observed_exposure": np.round(scores, 4),
            "beta_eloundou": np.round(
                np.clip(scores + rng.normal(0, 0.12, N_OCC), 0, 1), 4
            ),
        }
    )


def make_crosswalk(exposure: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Many-to-one O*NET-SOC to CPS occupation, with OES-style employment weights."""
    n_cps = int(N_OCC * 0.62)
    cps_codes = [f"{c:04d}" for c in rng.choice(
        np.arange(10, 9999), size=n_cps, replace=False
    )]
    assignment = rng.choice(cps_codes, size=len(exposure), replace=True)
    return pd.DataFrame(
        {
            "onetsoc_code": exposure["onetsoc_code"],
            "cps_occ": assignment,
            "oes_employment": rng.lognormal(9.5, 1.1, len(exposure)).round(0),
        }
    )


def make_cps(
    exposure: pd.DataFrame, crosswalk: pd.DataFrame, rng: np.random.Generator
) -> pd.DataFrame:
    """CPS-ASEC-shaped person records with an earnings-exposure gradient."""
    occ_exposure = (
        crosswalk.merge(exposure, on="onetsoc_code")
        .groupby("cps_occ")
        .apply(
            lambda g: np.average(
                g["observed_exposure"], weights=g["oes_employment"]
            ),
            include_groups=False,
        )
    )
    occ_codes = occ_exposure.index.to_numpy()
    occ_size = rng.lognormal(0.0, 0.9, len(occ_codes))
    p = occ_size / occ_size.sum()

    draw = rng.choice(len(occ_codes), size=N_PERSONS, p=p)
    occ = occ_codes[draw]
    expo = occ_exposure.to_numpy()[draw]

    # Log-normal wages with a positive exposure gradient plus idiosyncratic noise.
    mu = LOG_WAGE_MU + EARNINGS_GRADIENT * expo
    wage = np.exp(rng.normal(mu, LOG_WAGE_SIGMA, N_PERSONS))
    wage = np.round(np.clip(wage, 0, 2.0e6), 0)

    # Mimic CPS top-coding, which understates concentration at the top.
    topcode = np.quantile(wage, 0.997)
    wage = np.minimum(wage, topcode)

    return pd.DataFrame(
        {
            "year": 2025,
            "asecwt": np.round(rng.lognormal(7.4, 0.28, N_PERSONS), 2),
            "occ": occ,
            "incwage": wage,
            "age": rng.integers(16, 80, N_PERSONS),
            "sex": rng.integers(1, 3, N_PERSONS),
            "educ": rng.integers(2, 13, N_PERSONS),
        }
    )


def write_all(outdir: str | Path, seed: int = 20260726) -> dict[str, Path]:
    """Write the three synthetic inputs and return their paths."""
    rng = np.random.default_rng(seed)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    exposure = make_exposure(rng)
    crosswalk = make_crosswalk(exposure, rng)
    cps = make_cps(exposure, crosswalk, rng)

    paths = {
        "exposure": outdir / "synthetic_exposure.csv",
        "crosswalk": outdir / "synthetic_crosswalk.csv",
        "cps": outdir / "synthetic_cps_asec.csv",
    }
    exposure.to_csv(paths["exposure"], index=False)
    crosswalk.to_csv(paths["crosswalk"], index=False)
    cps.to_csv(paths["cps"], index=False)
    return paths
