#!/usr/bin/env python3
"""Request and download the CPS ASEC extract from IPUMS via their API.

This exists because the IPUMS web interface is a multi-step cart workflow that
is easy to get subtly wrong (in particular it defaults to fixed-width output,
which is painful to parse). Doing it through the API makes the extract
definition part of the repository, so the exact sample and variable list is
version-controlled alongside the analysis rather than living in someone's
browser history.

Setup, once:

    1. Register at https://cps.ipums.org/cps/  (free, approval is usually quick)
    2. Create an API key at https://account.ipums.org/api_keys
    3. export IPUMS_API_KEY="your key here"
    4. pip install ipumspy

Then:

    python scripts/01b_ipums_extract.py --submit      # queue the extract
    python scripts/01b_ipums_extract.py --download    # poll and fetch when ready

Or in one go, blocking until IPUMS finishes:

    python scripts/01b_ipums_extract.py --submit --wait --download

The extract number is written to data/raw/cps/.extract_id so --download can be
run later in a separate session.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

COLLECTION = "cps"

# ASEC samples. IPUMS sample IDs follow the pattern cps<year>_03s for the March
# ASEC supplement. Verify against https://cps.ipums.org/cps-action/samples
SAMPLES = ["cps2024_03s", "cps2025_03s"]

# Variables, grouped by what they are for. IPUMS always adds its own
# preselected identifiers (YEAR, SERIAL, MONTH, CPSID, ASECFLAG, PERNUM,
# CPSIDP, ASECWTH) on top of these.
VARIABLES = [
    # Weights. ASECWT is the person-level ASEC weight and is the one to use.
    "ASECWT",
    # Occupation. Request all three codings: OCC is contemporary, OCC2010 and
    # OCC1990 are harmonised over time. Which one you need depends on the
    # crosswalk target; Massenkoff and McCrory matched to OCC1990.
    "OCC",
    "OCC2010",
    "OCC1990",
    "IND",
    # Earnings.
    "INCWAGE",
    "INCBUS",
    "INCFARM",
    # Demographics.
    "AGE",
    "SEX",
    "EDUC",
    "RACE",
    "STATEFIP",
    # Labour force.
    "EMPSTAT",
    "CLASSWKR",
    "UHRSWORKLY",
    "WKSWORK1",
    # Household structure and non-wage income, needed if you move to TAXSIM.
    "MARST",
    "NCHILD",
    "INCTOT",
    "INCINT",
    "INCDIVID",
    "INCRENT",
    "INCSS",
    "INCRETIR",
]

DESCRIPTION = "AI fiscal exposure: CPS ASEC occupation, earnings and tax inputs"


def _client(api_key: str | None):
    try:
        from ipumspy import IpumsApiClient
    except ImportError:
        print(
            "ipumspy not installed. Run:  pip install ipumspy\n"
            "Or use the web interface, see data/README.md.",
            file=sys.stderr,
        )
        raise SystemExit(2) from None

    key = api_key or os.environ.get("IPUMS_API_KEY")
    if not key:
        print(
            "No API key. Create one at https://account.ipums.org/api_keys then:\n"
            '  export IPUMS_API_KEY="..."',
            file=sys.stderr,
        )
        raise SystemExit(2)
    return IpumsApiClient(key)


def build_extract():
    from ipumspy import MicrodataExtract

    return MicrodataExtract(
        collection=COLLECTION,
        samples=SAMPLES,
        variables=VARIABLES,
        description=DESCRIPTION,
        # CSV, not the fixed_width default. Fixed width needs the codebook to
        # parse and is the single most common way this step goes wrong.
        data_format="csv",
        data_structure={"rectangular": {"on": "P"}},
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--submit", action="store_true", help="queue a new extract")
    ap.add_argument("--wait", action="store_true", help="block until it is ready")
    ap.add_argument("--download", action="store_true", help="fetch a finished extract")
    ap.add_argument("--status", action="store_true", help="report status and exit")
    ap.add_argument("--extract-id", type=int, default=None)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--out", default="data/raw/cps")
    args = ap.parse_args()

    if not any([args.submit, args.download, args.status]):
        ap.error("choose at least one of --submit, --download, --status")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    id_file = out / ".extract_id"

    client = _client(args.api_key)
    extract_id = args.extract_id

    if args.submit:
        extract = build_extract()
        print(f"Submitting extract: {len(SAMPLES)} samples, "
              f"{len(VARIABLES)} variables, csv output")
        submitted = client.submit_extract(extract)
        extract_id = int(submitted.extract_id)
        id_file.write_text(str(extract_id) + "\n")
        print(f"  extract number {extract_id}, recorded in {id_file}")
        print("  IPUMS will email you when it is ready; typically minutes to hours.")

    if extract_id is None and id_file.exists():
        extract_id = int(id_file.read_text().strip())

    if extract_id is None:
        print("No extract id. Pass --extract-id or run --submit first.",
              file=sys.stderr)
        return 1

    if args.status:
        print(f"extract {extract_id}: "
              f"{client.extract_status(extract_id, collection=COLLECTION)}")

    if args.wait:
        print(f"Waiting on extract {extract_id}. Safe to interrupt; rerun with "
              "--download later.")
        client.wait_for_extract(extract_id, collection=COLLECTION)
        print("  ready")

    if args.download:
        status = client.extract_status(extract_id, collection=COLLECTION)
        if status != "completed":
            print(f"Extract {extract_id} is '{status}', not ready. "
                  "Rerun with --wait, or try again later.", file=sys.stderr)
            return 1
        client.download_extract(extract_id, collection=COLLECTION, download_dir=out)
        files = sorted(p.name for p in out.iterdir() if not p.name.startswith("."))
        print(f"Downloaded to {out}:")
        for f in files:
            print(f"  {f}")
        print("\nNext:")
        print("  python scripts/00_inspect_schemas.py --dir data/raw --full")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
