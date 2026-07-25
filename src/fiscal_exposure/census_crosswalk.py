"""Build the SOC 2018 to Census occupation crosswalk.

The Anthropic Economic Index publishes observed exposure on **6-digit SOC 2018**
codes (``11-1011``, ``11-1021``), not on 8-digit O\\*NET-SOC. The CPS identifies
occupations with **Census occupation codes**. So the join we need is
SOC 2018 -> Census 2018, and the authoritative source is the Census Bureau's own
code list:

    https://www.census.gov/topics/employment/industry-occupation/guidance/code-lists.html
    https://www2.census.gov/programs-surveys/demo/guidance/industry-occupation/2018-occupation-code-list-and-crosswalk.xlsx

This is the same file EIG used. Their repository does not ship it: the README
directs you to a Google Drive for raw inputs and lists "Census SOC to Census
occupation code crosswalk, downloaded from Census".

Three things about this workbook make a naive parse fail, and all three are
handled here.

**1. Layout.** The file has five sheets, the header sits under a title block,
cells are merged, and Excel renders text codes such as ``0010`` as the number
``10``. So columns are identified by *content* rather than by header name: every
column is scored by how many of its cells look like Census codes or SOC codes,
and the best pair wins. Sheets are ranked so the 2018 code list beats the
2010-to-2018 crosswalk, which would otherwise silently supply a 2010-basis
mapping.

**2. The SOC hierarchy.** SOC codes nest: ``11-0000`` major group, ``11-9000``
minor group, ``11-9030`` broad occupation, ``11-9031`` detailed occupation. A
trailing zero marks a *group*, not an occupation. The Census list frequently
maps one Census code to a broad group, while the exposure data is published at
the detailed level, so ``11-9030`` in the spreadsheet must expand to
``11-9031``, ``11-9032``, ``11-9033`` and ``11-9039``. Without this the match
rate sits around two thirds, and the codes that go missing are not random: they
are disproportionately the large white-collar categories this analysis is about.

**3. Explicit wildcards.** Some cells use forms such as ``11-30XX``.

Expansion is always resolved against the SOC codes actually present in the
exposure file, never invented, and each expansion route is counted separately so
the join can be audited.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

CENSUS_XLSX_URL = (
    "https://www2.census.gov/programs-surveys/demo/guidance/"
    "industry-occupation/2018-occupation-code-list-and-crosswalk.xlsx"
)

# 11-1011, and wildcard forms such as 11-30XX.
SOC_TOKEN = re.compile(r"(\d{2}-\d{2}[0-9X]{2})", re.IGNORECASE)
# Excel frequently renders the text code "0010" as the float 10.0.
FLOATY_INT = re.compile(r"^(\d+)\.0+$")
PURE_INT = re.compile(r"^\d{1,4}$")

# Sheet names to prefer, in order. Content still decides the columns; this only
# breaks ties between sheets, so that the 2018 code list is not beaten on volume
# by the 2010-to-2018 crosswalk, which maps an older Census vintage.
_SHEET_PREFERENCE = ("2018 census occ code list", "code list")
_SHEET_PENALTY = ("2010",)

# Shortest prefix we will expand from. "11-9" (minor group) is permitted;
# expanding a bare major group like "11-" would sweep in a whole occupational
# family and is refused.
_MIN_PREFIX_LEN = 4


@dataclass
class CrosswalkBuild:
    table: pd.DataFrame
    sheet: str
    census_col: int
    soc_col: int
    n_census_codes: int
    n_soc_codes: int
    n_exact: int
    n_group_expanded: int
    n_wildcard_expanded: int
    n_unresolved: int
    skipped_rows: int
    diagnostics: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"sheet {self.sheet!r}, census col {self.census_col}, "
            f"soc col {self.soc_col}: "
            f"{self.n_census_codes} Census codes, {self.n_soc_codes} SOC codes, "
            f"{len(self.table)} pairs\n"
            f"    {self.expansion_summary()}"
        )

    def expansion_summary(self) -> str:
        return (
            f"tokens resolved: {self.n_exact} exact, "
            f"{self.n_group_expanded} via SOC group, "
            f"{self.n_wildcard_expanded} via wildcard, "
            f"{self.n_unresolved} unresolved ({self.skipped_rows} rows skipped)"
        )

    # Retained so existing callers and tests keep working after the rename.
    @property
    def n_wildcards_expanded(self) -> int:
        return self.n_wildcard_expanded


def norm_census_code(value: object) -> str | None:
    """Normalise a cell to a 4-digit Census occupation code, or None.

    Handles the three forms these cells take: text ``"0010"``, integer ``10``,
    and Excel's float rendering ``"10.0"``.
    """
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "nat"}:
        return None
    if m := FLOATY_INT.match(s):
        s = m.group(1)
    if PURE_INT.match(s):
        code = s.zfill(4)
        return code if code != "0000" else None
    return None


def soc_tokens(value: object) -> list[str]:
    """Extract every SOC code appearing in a cell, including wildcard forms."""
    s = str(value)
    if not s or s.lower() in {"nan", "none"}:
        return []
    return [t.upper() for t in SOC_TOKEN.findall(s)]


def is_soc_group(token: str) -> bool:
    """True if the token denotes a SOC group rather than a detailed occupation.

    In the 2018 SOC, detailed occupations end in 1 through 9; a trailing zero
    marks a broad occupation, a minor group, or a major group.
    """
    return token.endswith("0") and "X" not in token.upper()


def expand_token(token: str, known_soc: set[str]) -> tuple[list[str], str]:
    """Resolve one SOC token against the codes present in the exposure data.

    Returns the resolved codes and a label for how they were obtained, one of
    ``exact``, ``group``, ``wildcard`` or ``unresolved``. Nothing is invented:
    every expansion is an intersection with ``known_soc``.
    """
    token = token.upper()
    if token in known_soc:
        return [token], "exact"

    if "X" in token:
        prefix = token.split("X")[0]
        matches = sorted(c for c in known_soc if c.startswith(prefix))
        return (matches, "wildcard") if matches else ([], "unresolved")

    if is_soc_group(token):
        prefix = token.rstrip("0")
        if len(prefix) >= _MIN_PREFIX_LEN:
            matches = sorted(c for c in known_soc if c.startswith(prefix))
            if matches:
                return matches, "group"

    # No known_soc supplied: keep the literal so the merge can still be attempted.
    if not known_soc:
        return [token], "exact"
    return [], "unresolved"


def _score_columns(raw: pd.DataFrame) -> tuple[int | None, int | None, dict]:
    """Pick the census-code and SOC-code columns by content."""
    census_hits: dict[int, int] = {}
    soc_hits: dict[int, int] = {}
    for j in range(raw.shape[1]):
        col = raw.iloc[:, j]
        census_hits[j] = int(sum(norm_census_code(v) is not None for v in col))
        soc_hits[j] = int(sum(len(soc_tokens(v)) > 0 for v in col))

    soc_col = max(soc_hits, key=lambda j: soc_hits[j]) if soc_hits else None
    if soc_col is not None and soc_hits[soc_col] == 0:
        soc_col = None

    candidates = {j: n for j, n in census_hits.items() if j != soc_col}
    census_col = max(candidates, key=lambda j: candidates[j]) if candidates else None
    if census_col is not None and candidates[census_col] == 0:
        census_col = None

    return census_col, soc_col, {"census_hits": census_hits, "soc_hits": soc_hits}


def _sheet_rank(name: str) -> int:
    """Higher is better. Used only to break ties between sheets."""
    low = str(name).strip().lower()
    if any(p in low for p in _SHEET_PENALTY):
        return -1
    for i, pref in enumerate(_SHEET_PREFERENCE):
        if pref in low:
            return len(_SHEET_PREFERENCE) - i
    return 0


def build_census_crosswalk(
    path: str | Path,
    *,
    known_soc: set[str] | None = None,
    sheet: int | str | None = None,
    census_col: int | None = None,
    soc_col: int | None = None,
) -> CrosswalkBuild:
    """Parse the Census occupation code list into ``[from_code, to_code]`` pairs.

    ``from_code`` is a 6-digit detailed SOC 2018 code, ``to_code`` a zero-padded
    4-digit Census occupation code.

    Pass ``known_soc`` (the SOC codes in the exposure file) so group and
    wildcard entries expand only to codes that actually exist. Pass
    ``census_col`` and ``soc_col`` as zero-based positions to override detection.
    """
    path = Path(path)
    book = pd.read_excel(path, sheet_name=sheet, header=None, dtype=object)
    if isinstance(book, pd.DataFrame):
        book = {str(sheet if sheet is not None else 0): book}

    known = {c.upper() for c in (known_soc or set())}
    candidates: list[CrosswalkBuild] = []
    diagnostics: list[str] = []

    for name, sheet_df in book.items():
        raw = sheet_df.dropna(how="all").dropna(axis=1, how="all")
        if raw.empty:
            diagnostics.append(f"sheet {name!r}: empty")
            continue

        auto_c, auto_s, hits = _score_columns(raw)
        c_col = census_col if census_col is not None else auto_c
        s_col = soc_col if soc_col is not None else auto_s
        top_c = sorted(hits["census_hits"].items(), key=lambda kv: -kv[1])[:3]
        top_s = sorted(hits["soc_hits"].items(), key=lambda kv: -kv[1])[:3]
        diagnostics.append(
            f"sheet {name!r} ({raw.shape[0]}x{raw.shape[1]}, rank "
            f"{_sheet_rank(name)}): census-like cols {top_c}, "
            f"soc-like cols {top_s}"
        )
        if c_col is None or s_col is None:
            continue

        rows: list[dict[str, str]] = []
        counts = {"exact": 0, "group": 0, "wildcard": 0, "unresolved": 0}
        skipped = 0
        for _, r in raw.iterrows():
            census = norm_census_code(r.iloc[c_col])
            if census is None:
                skipped += 1
                continue
            tokens = soc_tokens(r.iloc[s_col])
            if not tokens:
                skipped += 1
                continue
            for tok in tokens:
                resolved, how = expand_token(tok, known)
                counts[how] += 1
                for soc in resolved:
                    rows.append({"from_code": soc, "to_code": census})

        if not rows:
            continue
        table = pd.DataFrame(rows).drop_duplicates().reset_index(drop=True)
        candidates.append(
            CrosswalkBuild(
                table=table,
                sheet=str(name),
                census_col=int(c_col),
                soc_col=int(s_col),
                n_census_codes=int(table["to_code"].nunique()),
                n_soc_codes=int(table["from_code"].nunique()),
                n_exact=counts["exact"],
                n_group_expanded=counts["group"],
                n_wildcard_expanded=counts["wildcard"],
                n_unresolved=counts["unresolved"],
                skipped_rows=skipped,
            )
        )

    if not candidates:
        detail = "\n  ".join(diagnostics) or "no readable sheets"
        raise ValueError(
            f"Parsed zero crosswalk pairs from {path.name}.\n  {detail}\n"
            "Run  python scripts/01c_build_crosswalk.py --inspect  to dump the "
            "layout, then pass --census-col and --soc-col as zero-based "
            "positions."
        )

    # Sheet preference first, then coverage of the exposure universe, then size.
    def _key(b: CrosswalkBuild) -> tuple[int, int, int]:
        covered = len(set(b.table["from_code"]) & known) if known else 0
        return (_sheet_rank(b.sheet), covered, len(b.table))

    best = max(candidates, key=_key)
    best.diagnostics = diagnostics
    return best


def coverage_report(
    table: pd.DataFrame, known_soc: set[str]
) -> tuple[float, list[str]]:
    """Share of exposure SOC codes present in the crosswalk, and which are not."""
    if not known_soc:
        return 0.0, []
    present = set(table["from_code"])
    missing = sorted(known_soc - present)
    return (len(known_soc) - len(missing)) / len(known_soc), missing


def inspect_workbook(path: str | Path, max_rows: int = 25) -> None:
    """Print the top of every sheet, with per-column content scores.

    Use this when automatic detection fails. The scores report how many cells in
    each column parse as a Census code or contain a SOC code, which usually
    makes the right columns obvious at a glance.
    """
    path = Path(path)
    book = pd.read_excel(path, sheet_name=None, header=None, dtype=object)
    for name, df in book.items():
        clean = df.dropna(how="all").dropna(axis=1, how="all")
        print(f"\n=== sheet {name!r}  shape {clean.shape}  rank {_sheet_rank(name)} ===")
        with pd.option_context("display.max_colwidth", 40, "display.width", 200):
            print(clean.head(max_rows).to_string(max_cols=10))
        c_col, s_col, hits = _score_columns(clean)
        print(f"\n  cells parsing as a Census code, by column: {hits['census_hits']}")
        print(f"  cells containing a SOC code, by column:     {hits['soc_hits']}")
        print(f"  -> would use census_col={c_col}, soc_col={s_col}")
