#!/usr/bin/env python3
"""Fetch inputs, or generate synthetic stand-ins.

    python scripts/01_fetch.py --synthetic     # runs offline, instant
    python scripts/01_fetch.py --aei           # Anthropic Economic Index

CPS ASEC and the EIG crosswalk are not fetched automatically: IPUMS requires an
account and an extract request, and the EIG file is distributed from a landing
page. See data/README.md for both.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fiscal_exposure.provenance import Manifest  # noqa: E402
from fiscal_exposure.synthetic import write_all  # noqa: E402

AEI_REPO = "Anthropic/EconomicIndex"
AEI_SUBSET = "labor_market_impacts/*"


def fetch_aei(dest: Path) -> Path:
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print(
            "huggingface_hub not installed. Either:\n"
            "  pip install 'fiscal-exposure[fetch]'\n"
            "or download manually:\n"
            f"  https://huggingface.co/datasets/{AEI_REPO}/tree/main/labor_market_impacts\n"
            f"and place the files under {dest}",
            file=sys.stderr,
        )
        raise SystemExit(2) from None

    dest.mkdir(parents=True, exist_ok=True)
    path = snapshot_download(
        repo_id=AEI_REPO,
        repo_type="dataset",
        allow_patterns=[AEI_SUBSET],
        local_dir=str(dest),
    )
    return Path(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--aei", action="store_true")
    ap.add_argument("--raw-dir", default="data/raw")
    ap.add_argument("--manifest", default="output/manifest.json")
    ap.add_argument("--seed", type=int, default=20260726)
    args = ap.parse_args()

    if not (args.synthetic or args.aei):
        ap.error("choose --synthetic and/or --aei")

    raw = Path(args.raw_dir)
    manifest = Manifest(args.manifest)

    if args.synthetic:
        with manifest.step("01_fetch:synthetic", params={"seed": args.seed}) as rec:
            paths = write_all(raw, seed=args.seed)
            for p in paths.values():
                rec.add_output(p)
            rec.metric("files", len(paths))
        print(f"Wrote {len(paths)} synthetic files to {raw}:")
        for k, p in paths.items():
            print(f"  {k:10s} {p}")

    if args.aei:
        with manifest.step("01_fetch:aei", params={"repo": AEI_REPO}) as rec:
            out = fetch_aei(raw / "aei")
            n = sum(1 for _ in out.rglob("*") if _.is_file())
            rec.metric("files_downloaded", n)
        print(f"Downloaded {n} files to {out}")
        print("Next: python scripts/00_inspect_schemas.py --dir data/raw/aei --full")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
