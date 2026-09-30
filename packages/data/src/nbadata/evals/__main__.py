"""`python -m nbadata.evals` -- run the corpus and print the report card."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .corpus import load
from .mutate import generate
from .run import run
from .score import score
from .seasons import load_seasons


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate the engine against real trades.")
    ap.add_argument("--legs", type=Path, default=None)
    ap.add_argument("--min-season", default="2023-2024")
    ap.add_argument("--skip-mutations", action="store_true", help="corpus only, no mutation suite")
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

    if args.skip_mutations:
        return 1 if report.failures else 0

    print("\n" + "-" * 64 + "\n")
    result = score(generate(cases, seasons, base_cap), cases, seasons, base_cap)
    print(result.render())

    missed = len(result.detections) - result.detected
    wrong_reason = result.detected - result.right_reason
    return 1 if (report.failures or missed or wrong_reason) else 0


if __name__ == "__main__":
    sys.exit(main())
