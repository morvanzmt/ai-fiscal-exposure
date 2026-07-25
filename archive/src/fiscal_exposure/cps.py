"""CPS ASEC microdata.

Two supported sources, selected by ``cps.source`` in config:

``ipums``
    An extract from IPUMS CPS (https://cps.ipums.org/cps/), which supplies
    harmonised occupation codes. Preferred. Submit the extract first: it is the
    blocking dependency for the whole pipeline.

``census``
    The Census Bureau public use file
    (https://www.census.gov/data/datasets/time-series/demo/cps/cps-asec.html),
    which needs no registration and has no queue. Useful fallback.

Two caveats travel with this data and belong in any writeup. Occupation is
self-reported and measured with error. Wage income is top-coded, which
*understates* concentration at the top and therefore biases the headline result
toward zero.
"""

from __future__ import annotations

import pandas as pd

from fiscal_exposure.config import Config
from fiscal_exposure.exposure import read_any

REQUIRED = ("weight", "cps_occ", "wage", "year")


def load_cps(cfg: Config) -> pd.DataFrame:
    """Load CPS ASEC persons, normalised to ``[year, cps_occ, wage, weight]``.

    Additional columns present in the extract (age, sex, education, state) are
    carried through untouched for downstream use.
    """
    matches = sorted(cfg.paths.raw.glob(cfg.cps.file_glob))
    if not matches:
        raise FileNotFoundError(
            f"No CPS file matching {cfg.cps.file_glob!r} under {cfg.paths.raw}. "
            "See data/README.md."
        )
    frames = [read_any(p) for p in matches]
    df = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]
    df.columns = [str(c).lower() for c in df.columns]

    c = cfg.cps
    rename = {
        c.weight_col.lower(): "weight",
        c.occ_col.lower(): "cps_occ",
        c.wage_col.lower(): "wage",
        c.year_col.lower(): "year",
    }
    missing = [src for src in rename if src not in df.columns]
    if missing:
        raise KeyError(
            f"CPS columns {missing} absent. Available: {sorted(df.columns)[:40]}"
        )
    df = df.rename(columns=rename)

    df["cps_occ"] = df["cps_occ"].astype(str).str.strip()
    for col in ("weight", "wage"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["weight", "wage", "cps_occ"])

    return df.reset_index(drop=True)


def apply_universe(df: pd.DataFrame, cfg: Config) -> tuple[pd.DataFrame, dict]:
    """Restrict to the analysis universe and report what each filter removed.

    Restricting to positive wage earners is the right universe for a *wage tax
    base* question, but it is a choice, so it is reported rather than silent.
    """
    c = cfg.cps
    steps: dict[str, dict] = {}
    n0, w0 = len(df), float(df["weight"].sum())

    def _record(name: str, out: pd.DataFrame) -> pd.DataFrame:
        steps[name] = {
            "rows_before": n0 if not steps else steps[list(steps)[-1]]["rows_after"],
            "rows_after": len(out),
            "weighted_after": float(out["weight"].sum()),
        }
        return out

    work = df
    if "age" in work.columns:
        age = pd.to_numeric(work["age"], errors="coerce")
        work = _record("age", work[(age >= c.min_age) & (age <= c.max_age)])
    if c.require_positive_wage:
        work = _record("positive_wage", work[work["wage"] > 0])
    work = _record("positive_weight", work[work["weight"] > 0])

    summary = {
        "rows_initial": n0,
        "weighted_initial": w0,
        "rows_final": len(work),
        "weighted_final": float(work["weight"].sum()),
        "steps": steps,
    }
    return work.reset_index(drop=True), summary


def attach_exposure(
    cps: pd.DataFrame, mapping: pd.DataFrame, *, how: str = "left"
) -> pd.DataFrame:
    """Join occupation-level exposure onto CPS persons.

    A left join is deliberate: unmatched persons are retained with NaN exposure
    so that coverage can be measured on the weighted population rather than
    silently dropped.
    """
    out = cps.merge(mapping[["cps_occ", "exposure"]], on="cps_occ", how=how)
    return out
