"""
`python -m agent.router_cli` -- score the router against the labelled set (6.1).

Needs a key and spends money, so it is a command rather than a test. Reports
accuracy, per-class recall, and the tokens actually used, so the cost of a run
is a measured number (6.12) rather than an estimate.
"""

from __future__ import annotations

import argparse
import sys

from .llm import AnthropicCaller, Ledger
from .models import Role, model_for
from .router_evals import CASES, score


def main() -> int:
    parser = argparse.ArgumentParser(description="Score the question router.")
    parser.add_argument(
        "--model",
        default=None,
        help="pin the router model for this run, overriding the D15 default",
    )
    parser.add_argument("--limit", type=int, default=0, help="score only the first N cases")
    args = parser.parse_args()

    if args.model:
        import os

        os.environ["ANTHROPIC_MODEL_ROUTER"] = args.model

    selection = model_for(Role.ROUTER)
    print(f"router model: {selection.model}  ({selection.source})\n")

    ledger = Ledger()
    try:
        caller = AnthropicCaller(ledger=ledger)
    except RuntimeError as exc:
        print(exc)
        return 1

    cases = CASES[: args.limit] if args.limit else CASES
    report = score(caller, cases)
    print(report.render())
    print()
    print(ledger.render())
    return 0


if __name__ == "__main__":
    sys.exit(main())
