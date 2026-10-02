"""
Caps and per-request accounting (tasks 6.12, 6.13).

Two caps that fail differently on purpose: exceeding the tracing budget
degrades tracing, exceeding the spend budget refuses the request. These tests
hold that distinction, and hold that no price is ever invented.
"""

from __future__ import annotations

import pytest

from agent.budget import Budget, BudgetError, Price, measure
from agent.llm import Ledger, Usage
from agent.models import Role


def ledger(**by_role: Usage) -> Ledger:
    out = Ledger()
    for name, usage in by_role.items():
        out.record(Role(name), usage)
    return out


# -- rate limiting -------------------------------------------------------


def test_requests_are_limited_within_a_window():
    budget = Budget(max_requests=3, window_seconds=60)
    for i in range(3):
        budget.check_rate(now=100.0 + i)
    with pytest.raises(BudgetError, match="rate limit"):
        budget.check_rate(now=100.5)
    assert budget.refusals == 1


def test_the_window_slides_rather_than_resetting():
    """
    Fixed buckets let a burst straddling the boundary through at twice the
    rate. A sliding window does not.
    """
    budget = Budget(max_requests=2, window_seconds=10)
    budget.check_rate(now=0.0)
    budget.check_rate(now=9.9)
    with pytest.raises(BudgetError):
        budget.check_rate(now=10.0)
    budget.check_rate(now=10.1)  # the first has now aged out


def test_the_refusal_says_how_long_to_wait():
    budget = Budget(max_requests=1, window_seconds=60)
    budget.check_rate(now=0.0)
    with pytest.raises(BudgetError, match="try again in"):
        budget.check_rate(now=20.0)


# -- spend ---------------------------------------------------------------


def test_token_caps_refuse_further_requests():
    budget = Budget(max_input_tokens=1_000)
    budget.record("m", Usage(input_tokens=1_000))
    with pytest.raises(BudgetError, match="input token cap"):
        budget.check_spend()


def test_output_tokens_are_capped_separately():
    budget = Budget(max_output_tokens=100)
    budget.record("m", Usage(output_tokens=150))
    with pytest.raises(BudgetError, match="output token cap"):
        budget.check_spend()


def test_no_price_is_invented():
    """
    Per-token pricing changes, and a stale table would be worse than none --
    the whole point of a cap is that the operator can trust it. Unpriced, the
    budget enforces token ceilings, which are exact.
    """
    budget = Budget()
    assert budget.prices == {}
    assert not budget.spend_known
    budget.record("claude-sonnet-5", Usage(10_000, 500))
    assert budget.dollars == 0.0
    assert "not priced" in budget.render()
    assert "token ceilings are enforcing instead" in budget.render()


def test_dollars_are_computed_when_a_price_table_is_supplied():
    budget = Budget(prices={"m": Price(input_=3.0, output=15.0, cache_read=0.3, cache_write=3.75)})
    budget.record("m", Usage(input_tokens=1_000_000, output_tokens=0))
    assert budget.spend_known
    assert budget.dollars == pytest.approx(3.0)


def test_cache_reads_are_priced_apart_from_input():
    """
    With a 97% cache hit rate on the answer role, folding cache reads into
    input would misstate the bill badly.
    """
    price = Price(input_=3.0, output=15.0, cache_read=0.3, cache_write=3.75)
    cached = price.cost(Usage(cache_read_tokens=1_000_000))
    fresh = price.cost(Usage(input_tokens=1_000_000))
    assert cached == pytest.approx(0.3)
    assert fresh == pytest.approx(3.0)


def test_an_unpriced_model_does_not_silently_cost_nothing():
    """
    A model missing from the table contributes no dollars, which is why
    `spend_known` exists -- the token counts are still exact and still bind.
    """
    budget = Budget(prices={"known": Price(1.0, 1.0, 1.0, 1.0)})
    budget.record("unknown-model", Usage(1_000_000, 0))
    assert budget.dollars == 0.0
    assert budget.spent_input == 1_000_000


# -- the two caps fail differently ---------------------------------------


def test_the_tracing_cap_degrades_rather_than_refusing():
    """
    A trace is diagnostics. A question must not fail because the observability
    budget ran out.
    """
    budget = Budget(max_trace_events=5)
    assert budget.allow_trace(4)
    assert not budget.allow_trace(4)
    assert budget.traces_dropped == 4
    assert budget.trace_remaining == 1
    assert "traces dropped" in budget.render()


def test_dropped_traces_are_counted_so_silence_is_explicable():
    budget = Budget(max_trace_events=1)
    budget.allow_trace(5)
    assert budget.traces_dropped == 5


# -- per-request accounting (6.12) ---------------------------------------


def test_a_request_reports_calls_tools_tokens_and_latency():
    budget = Budget()
    cost = measure(
        budget,
        question="q",
        ledger=ledger(answer=Usage(10_000, 800, cache_read_tokens=5_000), router=Usage(450, 60)),
        tool_calls=3,
        seconds=9.4,
    )
    assert cost.model_calls == 2
    assert cost.tool_calls == 3
    assert cost.usage.input_tokens == 10_450
    assert cost.tokens == 11_310
    assert "9.4s" in cost.render()


def test_trace_events_are_counted_the_way_raindrop_bills_them():
    """
    The user turn, each model response, and each tool call (D13). A measured
    3.5 tool calls per question lands near 6 events, which is what the
    1,000-a-month budget was estimated against.
    """
    budget = Budget()
    cost = measure(
        budget,
        question="q",
        ledger=ledger(router=Usage(1, 1), intent=Usage(1, 1), answer=Usage(1, 1)),
        tool_calls=3,
        seconds=1.0,
    )
    assert cost.trace_events == 1 + 3 + 3
    assert budget.trace_events == 7


def test_an_unpriced_request_reports_none_not_zero():
    """Zero would read as free, which is a different claim from unknown."""
    cost = measure(
        Budget(), question="q", ledger=ledger(answer=Usage(1_000, 100)), tool_calls=0, seconds=1.0
    )
    assert cost.dollars is None
    assert "not priced" in cost.render()


def test_a_priced_request_attributes_cost_to_the_model_that_ran():
    budget = Budget(prices={"sonnet": Price(3.0, 15.0, 0.3, 3.75)})
    cost = measure(
        budget,
        question="q",
        ledger=ledger(answer=Usage(1_000_000, 0)),
        tool_calls=0,
        seconds=1.0,
        models={Role.ANSWER: "sonnet"},
    )
    assert cost.dollars == pytest.approx(3.0)
