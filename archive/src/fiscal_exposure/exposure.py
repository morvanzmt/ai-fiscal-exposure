"""Occupation-level AI exposure.

Primary source is the Anthropic Economic Index ``labor_market_impacts`` release
(CC-BY), which publishes the *observed exposure* measure of Massenkoff and
McCrory (2026): the share of an occupation's time-weighted tasks that are both
theoretically feasible for an LLM and observed in work-related Claude usage,
with automated use weighted above augmentative use.

The published column schema is pinned in ``config/config.yaml``. Until it is
pinned, :func:`detect_columns` will guess and report, and :func:`inspect_source`
prints everything needed to pin it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from fiscal_exposure.config import Config

# 15-1251.00 (O*NET-SOC, 8 digit) and 15-1251 (SOC, 6 digit)
ONET_SOC_RE = re.compile(r"^\d{2}-\d{4}\.\d{2}$")
SOC_RE = re.compile(r"^\d{2}-\d{4}$")

_OCC_NAME_HINTS = ("onet", "o*net", "soc", "occ", "code", "task_id")
_SCORE_NAME_HINTS = (
    "exposure",
    "coverage",
    "observed",
    "penetration",
    "score",
    "beta",
    "share",
    "fraction",
    "pct",
)
_EXCLUDE_SCORE_HINTS = ("year", "month", "count", "n_", "weight", "employment")


@dataclass(frozen=True)
class DetectedSchema:
    occ_col: str | None
    score_col: str | None
    occ_code_kind: str | None
    notes: list[str]

    def ok(self) -> bool:
        return self.occ_col is not None and self.score_col is not None


def _classify_codes(s: pd.Series) -> str | None:
    """Return 'onet_soc', 'soc2018' or None based on the shape of the values."""
    vals = s.dropna().astype(str).str.strip()
    if vals.empty:
        return None
    sample = vals.head(500)
    if (sample.str.match(ONET_SOC_RE)).mean() > 0.8:
        return "onet_soc"
    if (sample.str.match(SOC_RE)).mean() > 0.8:
        return "soc2018"
    return None


def detect_columns(df: pd.DataFrame) -> DetectedSchema:
    """Best-effort detection of the occupation-code and exposure-score columns.

    Detection is deliberately conservative and always reports its reasoning; it
    is a convenience for the first inspection pass, not a substitute for pinning
    the schema in config.
    """
    notes: list[str] = []

    occ_col, occ_kind = None, None
    for col in df.columns:
        kind = _classify_codes(df[col]) if df[col].dtype == object else None
        if kind:
            occ_col, occ_kind = col, kind
            notes.append(f"column {col!r} matches {kind} code pattern")
            break
    if occ_col is None:
        for col in df.columns:
            if any(h in col.lower() for h in _OCC_NAME_HINTS):
                occ_col = col
                notes.append(f"column {col!r} chosen on name hint only; verify")
                break

    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    candidates = []
    for col in numeric:
        low = col.lower()
        if any(h in low for h in _EXCLUDE_SCORE_HINTS):
            continue
        series = df[col].dropna()
        if series.empty:
            continue
        in_unit_interval = bool(series.min() >= 0 and series.max() <= 1)
        name_hit = any(h in low for h in _SCORE_NAME_HINTS)
        if in_unit_interval or name_hit:
            candidates.append((name_hit, in_unit_interval, col))
    candidates.sort(reverse=True)
    score_col = candidates[0][2] if candidates else None
    if score_col:
        notes.append(
            f"column {score_col!r} chosen as score "
            f"(name_hint={candidates[0][0]}, unit_interval={candidates[0][1]})"
        )
    if len(candidates) > 1:
        notes.append(
            "other score candidates: " + ", ".join(c[2] for c in candidates[1:6])
        )

    return DetectedSchema(occ_col, score_col, occ_kind, notes)


def inspect_source(directory: str | Path, max_files: int = 40) -> pd.DataFrame:
    """Walk a directory of released data and describe every tabular file.

    Run this first, before writing any merge logic, and paste the output when
    pinning the schema. Returns one row per file.
    """
    directory = Path(directory)
    rows = []
    paths = sorted(
        p
        for p in directory.rglob("*")
        if p.suffix.lower() in {".csv", ".tsv", ".parquet", ".json", ".jsonl", ".gz"}
    )
    for path in paths[:max_files]:
        info: dict[str, object] = {
            "path": str(path.relative_to(directory)),
            "size_mb": round(path.stat().st_size / 1e6, 2),
        }
        try:
            df = read_any(path, nrows=200)
            info["n_cols"] = df.shape[1]
            info["columns"] = ", ".join(map(str, df.columns[:25]))
            det = detect_columns(df)
            info["detected_occ_col"] = det.occ_col
            info["detected_score_col"] = det.score_col
            info["detected_code_kind"] = det.occ_code_kind
            info["notes"] = " | ".join(det.notes)
        except Exception as exc:  # noqa: BLE001 - inspection must never crash
            info["error"] = f"{type(exc).__name__}: {exc}"
        rows.append(info)
    return pd.DataFrame(rows)


def read_any(path: str | Path, nrows: int | None = None) -> pd.DataFrame:
    """Read csv/tsv/parquet/json into a DataFrame."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".gz":  # e.g. cps_00001.csv.gz from IPUMS
        inner = Path(path.stem).suffix.lower()
        sep = "\t" if inner == ".tsv" else ","
        return pd.read_csv(path, sep=sep, nrows=nrows, compression="gzip")
    if suffix == ".parquet":
        df = pd.read_parquet(path)
        return df.head(nrows) if nrows else df
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t", nrows=nrows)
    if suffix in {".json", ".jsonl"}:
        df = pd.read_json(path, lines=(suffix == ".jsonl"))
        return df.head(nrows) if nrows else df
    return pd.read_csv(path, nrows=nrows)


def load_exposure(cfg: Config) -> pd.DataFrame:
    """Load occupation-level exposure, normalised to ``[occ_code, exposure]``.

    Raises if the configured columns are absent, with a message pointing at
    :func:`inspect_source`.
    """
    matches = sorted(cfg.paths.raw.glob(cfg.exposure.file_glob))
    if not matches:
        raise FileNotFoundError(
            f"No exposure file matching {cfg.exposure.file_glob!r} under "
            f"{cfg.paths.raw}. Run scripts/01_fetch.py, then "
            f"scripts/00_inspect_schemas.py."
        )
    frames = [read_any(p) for p in matches]
    df = pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]

    occ_col, score_col = cfg.exposure.occ_col, cfg.exposure.score_col
    if occ_col is None or score_col is None:
        det = detect_columns(df)
        occ_col = occ_col or det.occ_col
        score_col = score_col or det.score_col
        if not (occ_col and score_col):
            raise ValueError(
                "Could not determine exposure schema. Detected: "
                f"{det}. Pin exposure.occ_col and exposure.score_col in config."
            )

    missing = [c for c in (occ_col, score_col) if c not in df.columns]
    if missing:
        raise KeyError(
            f"Columns {missing} not present in exposure data. "
            f"Available: {list(df.columns)}"
        )

    out = (
        df[[occ_col, score_col]]
        .rename(columns={occ_col: "occ_code", score_col: "exposure"})
        .dropna(subset=["occ_code", "exposure"])
    )
    out["occ_code"] = out["occ_code"].astype(str).str.strip()
    out["exposure"] = pd.to_numeric(out["exposure"], errors="coerce")
    out = out.dropna(subset=["exposure"])

    lo, hi = cfg.exposure.score_range
    if not out.empty:
        obs_lo, obs_hi = float(out["exposure"].min()), float(out["exposure"].max())
        if obs_lo < lo - 1e-9 or obs_hi > hi + 1e-9:
            raise ValueError(
                f"Exposure values in [{obs_lo}, {obs_hi}] fall outside the "
                f"configured range [{lo}, {hi}]. Check that {score_col!r} is the "
                "intended score column."
            )

    # Several O*NET-SOC rows can share one code across release vintages.
    out = out.groupby("occ_code", as_index=False)["exposure"].mean()
    return out.sort_values("occ_code").reset_index(drop=True)
