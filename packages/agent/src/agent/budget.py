"""
Rate limiting, spend caps and per-request accounting (tasks 6.12, 6.13).

A public URL in front of a model key is not deployable without these, and they
belong with the agent loop rather than bolted on at deploy time: the loop is
what knows how many calls a question cost.

**Two caps, not one.** Model spend is the obvious one. The second is Raindrop
events: the free tier allows 1,000 a month and this architecture is
deliberately tool-heavy, so a measured 3.5 tool calls per question works out
at about 6 events. That is roughly 140 questions a month (D13), and a cap that
only watched dollars would let tracing die silently a third of the way through
a demo.

**The two caps fail differently, on purpose.** Exceeding the tracing budget
*degrades tracing*; exceeding the spend budget *refuses the request*. A trace
is diagnostics, and losing one costs a developer some insight. A model call
costs money that is not recoverable, so that one stops.

**No prices are hard-coded.** Per-token pricing changes, and a stale table here
would be worse than none, because the whole point of a cap is that the operator
can trust it. Tokens are always counted; dollars are computed only when a price
table is supplied, and `spend_known` says which mode the budget is in. Unpriced,
it enforces token ceilings instead, which are exact.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field

from .llm import Ledger, Usage
from .models import Role

MILLION = 1_000_000


@dataclass(frozen=True, slots=True)
class Price:
    """
    Dollars per million tokens for one model, supplied by the operator.

    Cache reads are billed at a fraction of input and cache writes at a
    premium, so both are separate fields rather than folded into `input_`.
    With a 97% cache hit rate on the answer role (6.8), conflating them would
    misstate the bill badly.
    """

    input_: float
    output: float
    cache_read: float
    cache_write: float

    def cost(self, usage: Usage) -> float:
        return (
            usage.input_tokens * self.input_
            + usage.output_tokens * self.output
            + usage.cache_read_tokens * self.cache_read
            + usage.cache_write_tokens * self.cache_write
        ) / MILLION


ANTHROPIC_PRICES: dict[str, Price] = {
    # Dollars per million tokens, from Anthropic's published pricing.
    #
    # `cache_write` is the **5-minute** write price, because the breakpoint
    # this code sets is `{"type": "ephemeral"}`, which is the 5-minute TTL.
    # The 1-hour tier costs more to write and would be the wrong number here;
    # if the TTL ever changes, this has to change with it.
    "claude-haiku-4-5-20251001": Price(input_=1.0, output=5.0, cache_write=1.25, cache_read=0.10),
    "claude-sonnet-5": Price(input_=2.0, output=10.0, cache_write=2.50, cache_read=0.20),
    "claude-opus-5-5": Price(input_=4.0, output=20.0, cache_write=5.0, cache_read=0.20),
}
"""
Supplied rather than defaulted into `Budget`.

A budget still starts unpriced, so a deployment that forgets to pass this gets
exact token ceilings instead of a stale guess at dollars. Pricing changes; this
table is a convenience for the models D15 actually selected, not a claim that
it will stay current.

Note how much the cache read price matters here: at the 97% hit rate measured
in 6.8, Sonnet's answer-role input is billed mostly at $0.20 rather than $2.00.
"""


class BudgetError(RuntimeError):
    """
    The request was refused because a hard cap was reached.

    Raised rather than returned, because unlike every other failure here there
    is nothing partial to hand back: the work was not started.
    """


@dataclass
class Budget:
    """
    What a deployment may spend, and how fast.

    The request window is a sliding deque of timestamps rather than fixed
    buckets, so a burst straddling a boundary cannot push two windows' worth
    of requests through.
    """

    max_requests: int = 20
    window_seconds: float = 60.0
    max_input_tokens: int = 2_000_000
    max_output_tokens: int = 200_000
    max_trace_events: int = 1_000
    """Raindrop's Hobby tier allowance (D13)."""
    prices: dict[str, Price] = field(default_factory=dict)

    _requests: deque[float] = field(default_factory=deque, repr=False)
    spent_input: int = 0
    spent_output: int = 0
    spent_cache_read: int = 0
    spent_cache_write: int = 0
    trace_events: int = 0
    dollars: float = 0.0
    refusals: int = 0
    traces_dropped: int = 0

    # -- rate limiting ---------------------------------------------------

    def _prune(self, now: float) -> None:
        while self._requests and now - self._requests[0] > self.window_seconds:
            self._requests.popleft()

    def check_rate(self, now: float | None = None) -> None:
        moment = now if now is not None else time.monotonic()
        self._prune(moment)
        if len(self._requests) >= self.max_requests:
            self.refusals += 1
            wait = self.window_seconds - (moment - self._requests[0])
            raise BudgetError(
                f"rate limit: {self.max_requests} requests per {self.window_seconds:.0f}s "
                f"reached; try again in {wait:.0f}s"
            )
        self._requests.append(moment)

    # -- spend -----------------------------------------------------------

    @property
    def spend_known(self) -> bool:
        """
        Whether dollars are tracked, or only tokens.

        False when no price table was supplied. The caps still bind, on tokens
        instead, which is the honest fallback: a token ceiling is exact and a
        guessed price is not.
        """
        return bool(self.prices)

    def check_spend(self) -> None:
        if self.spent_input >= self.max_input_tokens:
            self.refusals += 1
            raise BudgetError(
                f"input token cap reached ({self.spent_input:,} of {self.max_input_tokens:,})"
            )
        if self.spent_output >= self.max_output_tokens:
            self.refusals += 1
            raise BudgetError(
                f"output token cap reached ({self.spent_output:,} of {self.max_output_tokens:,})"
            )

    def record(self, model: str, usage: Usage) -> None:
        self.spent_input += usage.input_tokens
        self.spent_output += usage.output_tokens
        self.spent_cache_read += usage.cache_read_tokens
        self.spent_cache_write += usage.cache_write_tokens
        price = self.prices.get(model)
        if price:
            self.dollars += price.cost(usage)

    def record_ledger(self, ledger: Ledger, models: dict[Role, str]) -> None:
        """Fold one completed request's ledger into the running budget."""
        for role, usage in ledger.by_role.items():
            self.record(models.get(role, ""), usage)

    # -- tracing ---------------------------------------------------------

    def allow_trace(self, events: int = 1) -> bool:
        """
        Whether this many trace events fit in the remaining allowance.

        Returns rather than raises: tracing is diagnostics, and a question must
        not fail because the observability budget ran out. Drops are counted,
        so silence is distinguishable from nothing having happened.
        """
        if self.trace_events + events > self.max_trace_events:
            self.traces_dropped += events
            return False
        self.trace_events += events
        return True

    @property
    def trace_remaining(self) -> int:
        return max(0, self.max_trace_events - self.trace_events)

    # -- reporting -------------------------------------------------------

    def render(self) -> str:
        lines = [
            "budget:",
            f"  input tokens   {self.spent_input:>9,} / {self.max_input_tokens:,}",
            f"  output tokens  {self.spent_output:>9,} / {self.max_output_tokens:,}",
            f"  cache read     {self.spent_cache_read:>9,}",
            f"  trace events   {self.trace_events:>9,} / {self.max_trace_events:,}",
        ]
        if self.spend_known:
            lines.append(f"  spend          {self.dollars:>9.4f} USD")
        else:
            lines.append(
                "  spend          not priced; token ceilings are enforcing instead. "
                "Supply a price table to see dollars."
            )
        if self.refusals:
            lines.append(f"  refused        {self.refusals:>9,} requests")
        if self.traces_dropped:
            lines.append(f"  traces dropped {self.traces_dropped:>9,} events")
        return "\n".join(lines)


@dataclass
class RequestCost:
    """What one question cost (task 6.12)."""

    question: str
    seconds: float
    model_calls: int
    tool_calls: int
    usage: Usage
    trace_events: int
    dollars: float | None = None
    """None when no price table was supplied -- not zero, which would read as free."""

    @property
    def tokens(self) -> int:
        return self.usage.input_tokens + self.usage.output_tokens

    def render(self) -> str:
        money = f"{self.dollars:.4f} USD" if self.dollars is not None else "not priced"
        return (
            f"{self.seconds:.1f}s, {self.model_calls} model calls, "
            f"{self.tool_calls} tool calls, "
            f"{self.usage.input_tokens:,} in / {self.usage.output_tokens:,} out, "
            f"{self.usage.cache_read_tokens:,} cached, "
            f"{self.trace_events} trace events, {money}"
        )


def measure(
    budget: Budget,
    *,
    question: str,
    ledger: Ledger,
    tool_calls: int,
    seconds: float,
    models: dict[Role, str] | None = None,
) -> RequestCost:
    """
    Fold one request into the budget and return what it cost.

    Trace events are counted the way Raindrop bills them (D13): the user turn,
    each model response, and each tool call.
    """
    assignment = models or {}
    budget.record_ledger(ledger, assignment)
    events = 1 + ledger.calls + tool_calls
    traced = budget.allow_trace(events)
    dollars: float | None = None
    if budget.spend_known:
        dollars = sum(
            budget.prices[assignment[role]].cost(usage)
            for role, usage in ledger.by_role.items()
            if assignment.get(role) in budget.prices
        )
    return RequestCost(
        question=question,
        seconds=seconds,
        model_calls=ledger.calls,
        tool_calls=tool_calls,
        usage=ledger.total,
        trace_events=events if traced else 0,
        dollars=dollars,
    )
