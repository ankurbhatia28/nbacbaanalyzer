"""
`python -m agent.cache_cli` -- measure what prompt caching is worth (task 6.8).

Runs each role's prompt shape twice with caching and twice without, and reports
the uncached input tokens either way. Two arms rather than one number, because
"caching saves X%" is meaningless without the comparison, and because it does
not help every role: a prefix below the model's minimum is ignored.

Spends a little money. Hence a command, not a test.
"""

from __future__ import annotations

import argparse
import sys
import time

from .llm import AnthropicCaller, JsonDict, Ledger, Usage
from .models import Role
from .router import system_prompt
from .tools import specs

PROBE: list[JsonDict] = [{"role": "user", "content": "Reply with the single word ok."}]
ANSWER_SYSTEM = (
    "You answer questions about the NBA Collective Bargaining Agreement using the "
    "tools provided. You never compute a figure yourself."
)


def _arm(*, cache: bool, role: Role, system: str, tools: list[JsonDict] | None, runs: int) -> Usage:
    """
    One arm of the comparison.

    The first call is discarded: with caching on it pays the write, and
    including it would report the cost of warming rather than the steady state
    a served request actually sees.
    """
    ledger = Ledger()
    caller = AnthropicCaller(ledger=ledger, cache=cache)
    for index in range(runs + 1):
        if index == 1:
            ledger = Ledger()
            caller.ledger = ledger
        caller(role=role, system=system, messages=PROBE, max_tokens=16, tools=tools)
        time.sleep(1)
    return ledger.total


def main() -> int:
    parser = argparse.ArgumentParser(description="Measure prompt caching.")
    parser.add_argument("--runs", type=int, default=3, help="steady-state calls per arm")
    args = parser.parse_args()

    shapes = [
        ("router (system only)", Role.ROUTER, system_prompt(), None),
        ("answer (system + 6 tools)", Role.ANSWER, ANSWER_SYSTEM, specs()),
    ]

    try:
        print(
            f"{'shape':<28} {'uncached in':>12} {'cached in':>10} {'from cache':>11} {'saved':>7}"
        )
        print("-" * 72)
        for label, role, system, tools in shapes:
            off = _arm(cache=False, role=role, system=system, tools=tools, runs=args.runs)
            on = _arm(cache=True, role=role, system=system, tools=tools, runs=args.runs)
            saved = 1 - (on.input_tokens / off.input_tokens) if off.input_tokens else 0.0
            print(
                f"{label:<28} {off.input_tokens:>12,} {on.input_tokens:>10,} "
                f"{on.cache_read_tokens:>11,} {saved:>7.0%}"
            )
    except RuntimeError as exc:
        print(exc)
        return 1

    print(
        "\n'uncached in' is what the API bills as fresh input. A shape whose prefix is below "
        "the model's minimum shows no change: the breakpoint is ignored, not charged."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
