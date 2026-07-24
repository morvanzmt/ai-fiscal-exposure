#!/usr/bin/env python3
"""Describe every tabular file under data/raw so the schema can be pinned.

Run this FIRST against the real download, before writing or trusting any merge
logic. Paste the output into config/config.yaml (exposure.occ_col,
exposure.score_col, crosswalk.from_col, crosswalk.to_col).

    python scripts/00_inspect_schemas.py
    python scripts/00_inspect_schemas.py --dir data/raw/aei --full
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fiscal_exposure.exposure import (  # noqa: E402
    detect_columns,
    inspect_source,
    read_any,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", default="data/raw", help="directory to walk")
    ap.add_argument("--full", action="store_true", help="also print head() per file")
    ap.add_argument("--max-files", type=int, default=40)
    args = ap.parse_args()

    root = Path(args.dir)
    if not root.exists():
        print(f"No such directory: {root}", file=sys.stderr)
        print("Run scripts/01_fetch.py, or see data/README.md.", file=sys.stderr)
        return 1

    pd.set_option("display.max_colwidth", 200)
    pd.set_option("display.width", 200)

    report = inspect_source(root, max_files=args.max_files)
    if report.empty:
        print(f"No tabular files found under {root}.")
        return 1

    print(f"\n{'=' * 78}\nFILES UNDER {root}\n{'=' * 78}")
    for _, row in report.iterrows():
        print(f"\n  {row['path']}  ({row.get('size_mb', '?')} MB)")
        if "error" in row and pd.notna(row.get("error")):
            print(f"    ERROR: {row['error']}")
            continue
        print(f"    columns ({row.get('n_cols')}): {row.get('columns')}")
        print(f"    -> occ col   : {row.get('detected_occ_col')}")
        print(f"    -> score col : {row.get('detected_score_col')}")
        print(f"    -> code kind : {row.get('detected_code_kind')}")
        if row.get("notes"):
            print(f"    notes: {row['notes']}")

    if args.full:
        print(f"\n{'=' * 78}\nSAMPLES\n{'=' * 78}")
        for _, row in report.iterrows():
            path = root / str(row["path"])
            try:
                df = read_any(path, nrows=5)
            except Exception as exc:  # noqa: BLE001
                print(f"\n  {row['path']}: unreadable ({exc})")
                continue
            print(f"\n  {row['path']}\n{'-' * 78}")
            print(df.to_string(max_cols=12))
            det = detect_columns(df)
            if det.occ_col and det.occ_col in df.columns:
                vals = df[det.occ_col].astype(str).head(5).tolist()
                print(f"    sample codes: {vals}")

    print(
        "\nNext: pin exposure.occ_col / exposure.score_col and the crosswalk "
        "columns in config/config.yaml, then run scripts/02_build_dataset.py.\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
