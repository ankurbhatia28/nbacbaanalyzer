"""`python -m nbadata.evals` -- run the corpus and print the report card."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .corpus import load
from .run import run
from .seasons import load_seasons


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate the engine against real trades.")
    ap.add_argument("--legs", type=Path, default=None)
    ap.add_argument("--min-season", default="2023-2024")
    args = ap.parse_args()

    cases = load(args.legs, min_season=args.min_season)
    seasons, base_cap = load_seasons()
    if not cases:
        print("no cases loaded; run scraper/salaryswish_scrape.py --what trades first")
        return 1
    if not base_cap:
        print("no 2023-24 cap figure; the Expanded exception cannot be computed")
        return 1

    report = run(cases, seasons, base_cap)
    print(report.render())
    return 1 if report.failures else 0


if __name__ == "__main__":
    sys.exit(main())
