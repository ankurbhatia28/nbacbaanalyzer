"""`python -m nbadata.evals` -- run the corpus and print the report card."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from nbadata.db import open_readonly
from nbadata.ingest.load import load as load_csvs

from .corpus import load
from .mutate import generate
from .queries import QueryEvalReport, run_query_evals
from .run import run
from .score import score
from .seasons import load_seasons


def _query_evals(csv_dir: Path) -> QueryEvalReport | None:
    """
    Run the golden questions against a freshly built database.

    Built into a temporary file rather than read from a committed artifact:
    the database is a build output (ADR-004), and an eval that passes against a
    stale copy proves nothing about the current data.
    """
    if not (csv_dir / "contracts.csv").exists():
        return None
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "evals.db"
        load_csvs(csv_dir, db)
        return run_query_evals(open_readonly(db))


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate the engine against real trades.")
    ap.add_argument("--legs", type=Path, default=None)
    ap.add_argument("--min-season", default="2023-2024")
    ap.add_argument("--skip-mutations", action="store_true", help="corpus only, no mutation suite")
    ap.add_argument(
        "--csv-dir",
        type=Path,
        default=Path("scraper/out"),
        help="scraper output, for the query eval set",
    )
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

    queries = _query_evals(args.csv_dir)
    if queries is not None:
        print("\n" + "-" * 64 + "\n")
        print(queries.render())

    missed = len(result.detections) - result.detected
    wrong_reason = result.detected - result.right_reason
    query_failures = len(queries.failed) + len(queries.errored) if queries else 0
    return 1 if (report.failures or missed or wrong_reason or query_failures) else 0


if __name__ == "__main__":
    sys.exit(main())
