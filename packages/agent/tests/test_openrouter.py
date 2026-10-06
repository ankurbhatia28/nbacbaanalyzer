"""
The free fallback (D23), tested without a key or a network.

OpenRouter is stubbed at the HTTP boundary; the answer loop is driven by
stub callers. What matters is when the switch happens, that it does not
happen for the wrong reasons, and that the reader is told.
"""

from __future__ import annotations

from typing import Any

import anthropic
import httpx2
import pytest

from agent.answer import answer
from agent.budget import Budget
from agent.card import WarningKind, build
from agent.llm import Reply, Usage
from agent.models import Role
from agent.openrouter import (
    REASONING_HEADROOM,
    FallbackCaller,
    FallbackUnavailableError,
    OpenRouterCaller,
    _to_openai,
    anthropic_unavailable,
)
from agent.tools import Resources

FREE = "vendor/some-model:free"


class Response:
    def __init__(self, status: int, payload: Any) -> None:
        self.status_code = status
        self._payload = payload

    def json(self) -> Any:
        return self._payload


def ok(message: dict[str, Any], finish: str = "stop") -> Response:
    return Response(
        200,
        {
            "choices": [{"message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        },
    )


class Post:
    """Replays responses in order and records what was sent."""

    def __init__(self, *responses: Response) -> None:
        self.responses = list(responses)
        self.sent: list[dict[str, Any]] = []

    def __call__(self, url: str, *, json: dict[str, Any], headers: dict[str, str]) -> Response:
        self.sent.append(json)
        return self.responses.pop(0)


def caller(post: Post, **kw: Any) -> OpenRouterCaller:
    return OpenRouterCaller(api_key="k", model=FREE, post=post, sleep=lambda _: None, **kw)


# -- translation ------------------------------------------------------------


def test_an_anthropic_tool_round_becomes_openai_messages() -> None:
    messages = [
        {"role": "user", "content": "q"},
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "hm", "signature": "s"},
                {"type": "text", "text": "looking"},
                {"type": "tool_use", "id": "t1", "name": "define_term", "input": {"term": "Room"}},
            ],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "t1", "content": '{"ok": true}'}],
        },
    ]
    out = _to_openai("sys", messages)
    assert out[0] == {"role": "system", "content": "sys"}
    assert out[2]["content"] == "looking"  # the thinking block is dropped
    assert out[2]["tool_calls"][0]["function"] == {
        "name": "define_term",
        "arguments": '{"term": "Room"}',
    }
    assert out[3] == {"role": "tool", "tool_call_id": "t1", "content": '{"ok": true}'}


def test_a_tool_call_comes_back_as_anthropic_blocks() -> None:
    post = Post(
        ok(
            {
                "content": None,
                "tool_calls": [
                    {
                        "id": "c1",
                        "function": {"name": "lookup_player", "arguments": '{"name": "x"}'},
                    },
                    {"id": "c2", "function": {"name": "query_league_data", "arguments": "[1]"}},
                ],
            },
            finish="tool_calls",
        )
    )
    reply = caller(post)(role=Role.ANSWER, system="s", messages=[{"role": "user", "content": "q"}])
    assert reply.stop_reason == "tool_use"
    assert [(r.name, r.arguments) for r in reply.tool_requests] == [
        ("lookup_player", {"name": "x"}),
        ("query_league_data", {}),  # not an object: left for tools.call to reject
    ]
    assert reply.raw_content[0] == {
        "type": "tool_use",
        "id": "c1",
        "name": "lookup_player",
        "input": {"name": "x"},
    }
    assert reply.usage == Usage(7, 3)


def test_reasoning_gets_headroom_on_top_of_max_tokens() -> None:
    post = Post(ok({"content": "{}"}))
    caller(post)(
        role=Role.ROUTER, system="s", messages=[{"role": "user", "content": "q"}], max_tokens=300
    )
    assert post.sent[0]["max_tokens"] == 300 + REASONING_HEADROOM


# -- reliability and money ----------------------------------------------------


def test_a_burst_of_503s_is_ridden_out() -> None:
    post = Post(Response(503, {}), Response(200, {"error": {"code": 503}}), ok({"content": "hi"}))
    reply = caller(post)(role=Role.ANSWER, system="s", messages=[{"role": "user", "content": "q"}])
    assert reply.text == "hi"


def test_it_gives_up_with_an_error_that_says_why() -> None:
    post = Post(*[Response(503, {})] * 4)
    with pytest.raises(FallbackUnavailableError, match="503"):
        caller(post)(role=Role.ANSWER, system="s", messages=[{"role": "user", "content": "q"}])


def test_a_paid_model_is_refused_so_the_credit_is_never_spent() -> None:
    with pytest.raises(ValueError, match="not a free model"):
        OpenRouterCaller(api_key="k", model="vendor/paid-model", post=Post())


# -- when to switch -----------------------------------------------------------


def _status_error(cls: type[anthropic.APIStatusError], status: int, message: str) -> Exception:
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls(message, response=httpx2.Response(status, request=request), body=None)


def test_spend_limits_rate_limits_and_overload_switch() -> None:
    limit = _status_error(
        anthropic.BadRequestError, 400, "You have reached your specified workspace API usage limits"
    )
    assert anthropic_unavailable(limit) is not None
    assert anthropic_unavailable(_status_error(anthropic.RateLimitError, 429, "slow down"))
    assert anthropic_unavailable(_status_error(anthropic.InternalServerError, 529, "overloaded"))


def test_a_malformed_request_does_not_switch_it_surfaces() -> None:
    bad = _status_error(anthropic.BadRequestError, 400, "messages.0.content: field required")
    assert anthropic_unavailable(bad) is None
    assert anthropic_unavailable(ValueError("a bug")) is None


class Named:
    def __init__(self, model: str, fail: Exception | None = None) -> None:
        self.model, self.fail, self.calls = model, fail, 0

    def __call__(self, **kw: Any) -> Reply:
        self.calls += 1
        if self.fail:
            raise self.fail
        return Reply("ok", Usage(1, 1), self.model)


class Clock:
    now = 0.0

    def __call__(self) -> float:
        return self.now


def test_the_switch_is_sticky_until_the_cooldown_then_anthropic_is_retried() -> None:
    clock = Clock()
    primary, fallback = Named("sonnet", fail=RuntimeError("limit")), Named("free")
    switch = FallbackCaller(primary, fallback, classify=lambda e: ("limit", 60.0), clock=clock)
    kw: dict[str, Any] = dict(role=Role.ANSWER, system="s", messages=[])

    assert switch(**kw).model == "free"
    assert switch(**kw).model == "free"
    assert primary.calls == 1  # not asked again inside the cooldown

    clock.now = 61.0
    primary.fail = None
    assert switch(**kw).model == "sonnet"
    assert not switch.engaged


def test_an_unclassified_error_is_raised_not_hidden() -> None:
    switch = FallbackCaller(
        Named("sonnet", fail=ValueError("bug")), Named("free"), classify=lambda e: None
    )
    with pytest.raises(ValueError):
        switch(role=Role.ANSWER, system="s", messages=[])


# -- the answer loop ------------------------------------------------------------


class Plain:
    """Router, intent and answer replies for a question answered in one turn."""

    def __init__(self, model: str) -> None:
        self.model = model

    def __call__(self, *, role: Role, **kw: Any) -> Reply:
        if role is Role.ROUTER:
            return Reply('{"intents": ["data"], "reason": "r"}', Usage(1, 1), self.model)
        if role is Role.INTENT:
            return Reply('{"provisions": []}', Usage(1, 1), self.model)
        return Reply("An answer.", Usage(1, 1), self.model, stop_reason="end_turn")


@pytest.fixture
def res() -> Resources:
    import sqlite3

    cba = sqlite3.connect(":memory:")
    # The intent step reads the vocabulary; nothing else here touches the index.
    cba.execute("CREATE TABLE vocabulary (name TEXT PRIMARY KEY, citation TEXT, kind TEXT)")
    return Resources(league=sqlite3.connect(":memory:"), cba=cba, base_season_cap=0)


def test_past_the_spend_cap_the_fallback_answers_and_the_card_says_so(res: Resources) -> None:
    spent = Budget(max_input_tokens=1)
    spent.spent_input = 1
    switch = FallbackCaller(
        Named("sonnet", fail=AssertionError("must not be called")), Plain("free")
    )

    verdict = answer(switch, question="q", res=res, budget=spent)

    assert verdict.over_budget is None
    assert verdict.text == "An answer."
    assert verdict.fallback_model == "free"
    assert "spend cap" in (verdict.fallback or "")
    warnings = {w.kind for w in build(verdict).warnings}
    assert WarningKind.FALLBACK_MODEL in warnings


def test_without_a_fallback_the_spend_cap_still_refuses(res: Resources) -> None:
    spent = Budget(max_input_tokens=1)
    spent.spent_input = 1
    verdict = answer(Plain("sonnet"), question="q", res=res, budget=spent)
    assert verdict.over_budget is not None
    assert verdict.fallback is None


def test_the_rate_limit_refuses_even_with_a_fallback(res: Resources) -> None:
    busy = Budget(max_requests=1)
    busy.check_rate()  # the window is full
    switch = FallbackCaller(Plain("sonnet"), Plain("free"))
    verdict = answer(switch, question="q", res=res, budget=busy)
    assert verdict.over_budget is not None and "rate limit" in verdict.over_budget


def test_an_ordinary_answer_carries_no_fallback_warning(res: Resources) -> None:
    switch = FallbackCaller(Plain("sonnet"), Plain("free"))
    verdict = answer(switch, question="q", res=res, budget=Budget())
    assert verdict.fallback is None
    assert WarningKind.FALLBACK_MODEL not in {w.kind for w in build(verdict).warnings}
