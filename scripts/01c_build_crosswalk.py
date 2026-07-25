#!/usr/bin/env python3
"""Fetch and build the SOC 2018 to Census occupation crosswalk.

    python scripts/01c_build_crosswalk.py                 # download and build
    python scripts/01c_build_crosswalk.py --inspect       # dump sheet layout
    python scripts/01c_build_crosswalk.py --xlsx path.xlsx

Writes ``data/raw/crosswalk/soc2018_to_census2018.csv`` with columns
``from_code`` (SOC 2018) and ``to_code`` (4-digit Census occupation code), which
is what ``config`` points at.

The Anthropic Economic Index publishes exposure on 6-digit SOC 2018 codes, and
the CPS uses Census occupation codes, so this is the join. If the automatic
download is blocked, grab the file by hand from

    https://www.census.gov/topics/employment/industry-occupation/guidance/code-lists.html

under "2018 Census Occupation Code Lists (Derived from the 2018 SOC)", save it
into data/raw/crosswalk/, and rerun with --xlsx.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd  # noqa: E402

from fiscal_exposure.census_crosswalk import (  # noqa: E402
    CENSUS_XLSX_URL,
    build_census_crosswalk,
    inspect_workbook,
)
from fiscal_exposure.provenance import Manifest  # noqa: E402

DEST_DIR = Path("data/raw/crosswalk")
XLSX_NAME = "2018-occupation-code-list-and-crosswalk.xlsx"
OUT_NAME = "soc2018_to_census2018.csv"


def download(dest: Path) -> Path:
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {CENSUS_XLSX_URL}")
    req = urllib.request.Request(
        CENSUS_XLSX_URL, headers={"User-Agent": "Mozilla/5.0 (research script)"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, dest.open("wb") as fh:
            fh.write(resp.read())
    except Exception as exc:  # noqa: BLE001
        print(
            f"\nDownload failed ({type(exc).__name__}: {exc}).\n"
            "Get it by hand instead:\n"
            "  https://www.census.gov/topics/employment/industry-occupation/"
            "guidance/code-lists.html\n"
            '  -> "2018 Census Occupation Code Lists (Derived from the 2018 SOC)"\n'
            f"  save to {dest}, then rerun with --xlsx {dest}",
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    print(f"  saved to {dest} ({dest.stat().st_size / 1e6:.2f} MB)")
    return dest


def load_known_soc(exposure_path: Path) -> set[str]:
    """SOC codes present in the exposure file, used to expand wildcard entries."""
    if not exposure_path.exists():
        print(f"  (no exposure file at {exposure_path}; wildcards left literal)")
        return set()
    df = pd.read_csv(exposure_path, dtype=str)
    col = "occ_code" if "occ_code" in df.columns else df.columns[0]
    return {str(v).strip().upper() for v in df[col].dropna()}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--xlsx", default=None, help="use a local file instead")
    ap.add_argument("--inspect", action="store_true", help="dump sheet layout")
    ap.add_argument("--sheet", default=None, help="sheet name or index; default all")
    ap.add_argument("--census-col", type=int, default=None,
                    help="zero-based column position, overrides detection")
    ap.add_argument("--soc-col", type=int, default=None,
                    help="zero-based column position, overrides detection")
    ap.add_argument(
        "--exposure",
        default="data/raw/aei/labor_market_impacts/job_exposure.csv",
    )
    ap.add_argument("--manifest", default="output/manifest.json")
    args = ap.parse_args()

    xlsx = Path(args.xlsx) if args.xlsx else DEST_DIR / XLSX_NAME
    if not xlsx.exists():
        download(xlsx)

    if args.inspect:
        inspect_workbook(xlsx)
        return 0

    known = load_known_soc(Path(args.exposure))
    if known:
        print(f"  {len(known)} SOC codes in the exposure file")

    sheet = args.sheet
    if sheet is not None and str(sheet).isdigit():
        sheet = int(sheet)

    manifest = Manifest(args.manifest)
    with manifest.step("01c_crosswalk", params={"source": CENSUS_XLSX_URL}) as rec:
        rec.add_input(xlsx)
        build = build_census_crosswalk(
            xlsx,
            known_soc=known,
            sheet=sheet,
            census_col=args.census_col,
            soc_col=args.soc_col,
        )
        out = DEST_DIR / OUT_NAME
        out.parent.mkdir(parents=True, exist_ok=True)
        build.table.to_csv(out, index=False)
        rec.add_output(out)
        rec.metric("n_pairs", len(build.table))
        rec.metric("n_soc_codes", build.n_soc_codes)
        rec.metric("n_census_codes", build.n_census_codes)
        rec.metric("wildcards_expanded", build.n_wildcards_expanded)

    print(f"  {build.summary()}")
    for line in build.diagnostics:
        print(f"    {line}")

    if known:
        in_cw = set(build.table["from_code"])
        covered = len(in_cw & known) / len(known)
        print(f"\n  {covered:.1%} of the {len(known)} exposure SOC codes "
              "appear in the crosswalk")
        missing = sorted(known - in_cw)
        if missing:
            print(f"  {len(missing)} unmatched, e.g. {missing[:8]}")
        if covered < 0.80:
            print("\n  WARNING: coverage below 80%. Check the sheet and columns "
                  "with --inspect before trusting downstream results.")

    print(f"\nWrote {DEST_DIR / OUT_NAME}")
    print("Next: python scripts/02_build_dataset.py --config config/config.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
