"""`python -m agent.adversarial_cli` -- run the adversarial set (6.11). Spends money."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

from nbadata.db import open_readonly
from nbadata.ingest.load import load as load_csvs
from rag import index as ix
from rag.chunks import build as build_chunks
from rag.crossrefs import build as build_graph
from rag.definitions import build as build_definitions
from rag.outline import DEFAULT_PDF, load

from .adversarial import PROBES, score
from .llm import AnthropicCaller, Ledger
from .models import describe
from .tools import Resources

CSV_DIR = Path(__file__).resolve().parents[4] / "scraper" / "out"
BASE_CAP = 136_021_000


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the adversarial evals.")
    parser.add_argument("--model", default=None, help="pin the answer model for this run")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if args.model:
        os.environ["ANTHROPIC_MODEL_ANSWER"] = args.model

    if not DEFAULT_PDF.exists() or not (CSV_DIR / "contracts.csv").exists():
        print("needs the CBA PDF and scraper output")
        return 1

    print("models:")
    print(describe())
    print()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        outline = load()
        ix.build(
            root / "cba.db",
            build_chunks(outline),
            build_definitions(outline),
            build_graph(outline),
            outline,
        )
        load_csvs(CSV_DIR, root / "league.db")
        res = Resources(
            league=open_readonly(root / "league.db"),
            cba=ix.open_index(root / "cba.db"),
            base_season_cap=BASE_CAP,
        )
        ledger = Ledger()
        try:
            caller = AnthropicCaller(ledger=ledger)
        except RuntimeError as exc:
            print(exc)
            return 1

        probes = PROBES[: args.limit] if args.limit else PROBES
        started = time.time()
        report = score(caller, res, probes)
        elapsed = time.time() - started

        print(report.render())
        print()
        print(ledger.render())
        print(f"\n  {elapsed:.0f}s wall clock, {elapsed / max(len(probes), 1):.1f}s per question")

    return 1 if report.fabricated else 0


if __name__ == "__main__":
    sys.exit(main())
