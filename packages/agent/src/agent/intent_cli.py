"""`python -m agent.intent_cli` -- score intent extraction (task 6.3). Spends money."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from nbadata.db import open_readonly
from nbadata.ingest.load import load as load_csvs
from rag import index as ix
from rag.chunks import build as build_chunks
from rag.crossrefs import build as build_graph
from rag.definitions import build as build_definitions
from rag.outline import DEFAULT_PDF, load

from .intent_evals import score
from .llm import AnthropicCaller, Ledger
from .models import Role, model_for

CSV_DIR = Path(__file__).resolve().parents[4] / "scraper" / "out"


def main() -> int:
    parser = argparse.ArgumentParser(description="Score intent extraction.")
    parser.add_argument("--model", default=None, help="pin the intent model for this run")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    if args.model:
        os.environ["ANTHROPIC_MODEL_INTENT"] = args.model

    if not DEFAULT_PDF.exists() or not (CSV_DIR / "contracts.csv").exists():
        print("needs the CBA PDF and scraper output")
        return 1

    selection = model_for(Role.INTENT)
    print(f"intent model: {selection.model}  ({selection.source})\n")

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
        cba = ix.open_index(root / "cba.db")
        league = open_readonly(root / "league.db")

        ledger = Ledger()
        try:
            caller = AnthropicCaller(ledger=ledger)
        except RuntimeError as exc:
            print(exc)
            return 1

        from rag.evals import RULES

        questions = tuple(RULES[: args.limit]) if args.limit else tuple(RULES)
        report = score(caller, cba=cba, league=league, questions=questions)
        print(report.render())
        print()
        print(ledger.render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
