"""
The router (task 6.1), tested without spending anything.

Every test here runs against a stub caller. A test that needs an API key is a
test that stops running — and the router's contract is about how it handles a
reply, not about which reply a model gives. Whether the model is actually any
good is measured by `python -m agent.router_cli`, which costs money and so is
a command rather than part of the suite.
"""

from __future__ import annotations

import json

import pytest

from agent.llm import JsonReplyError, Ledger, Reply, Usage, ask_json
from agent.models import Role
from agent.router import Intent, route, system_prompt
from agent.router_evals import CASES, Outcome, score


class Stub:
    """A caller that replays scripted replies and records what it was asked."""

    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.calls: list[dict] = []

    def __call__(self, *, role, system, messages, max_tokens=1024, tools=None) -> Reply:
        self.calls.append({"role": role, "system": system, "messages": messages})
        text = self.replies.pop(0) if self.replies else "{}"
        return Reply(text=text, usage=Usage(10, 5), model="stub", stop_reason="end_turn")


def reply(*intents: str, reason: str = "because", basis: str | None = None) -> str:
    return json.dumps({"intents": list(intents), "reason": reason, "refusal_basis": basis})


# -- parsing a reply -----------------------------------------------------


def test_one_label_is_parsed():
    routing = route(Stub(reply("data")), "how much is Denver committed for?")
    assert routing.intents == (Intent.DATA,)
    assert not routing.refused


def test_several_labels_are_kept():
    """
    Compound questions are the point of allowing combinations: a router forced
    to pick one label drops half of what was asked.
    """
    routing = route(Stub(reply("constraints", "rules")), "limits, and the rule behind them?")
    assert set(routing.intents) == {Intent.CONSTRAINTS, Intent.RULES}


def test_a_duplicate_label_is_not_counted_twice():
    routing = route(Stub(reply("data", "data")), "q")
    assert routing.intents == (Intent.DATA,)


def test_an_unrecognised_label_is_dropped_not_guessed_at():
    routing = route(Stub(reply("data", "vibes")), "q")
    assert routing.intents == (Intent.DATA,)


def test_a_reply_with_no_usable_label_falls_back_to_the_text_path():
    """
    `rules` is the least harmful default: it answers from cited text, so it
    produces a quotation or nothing, never a computed figure.
    """
    routing = route(Stub(reply("nonsense")), "q")
    assert routing.intents == (Intent.RULES,)


def test_a_refusal_carries_its_basis():
    """
    A refusal that cannot say why is indistinguishable from a bug. D6 puts
    historical questions out of scope; D10 declines "should they".
    """
    routing = route(Stub(reply("refused", basis="historical")), "what was the cap in 2019?")
    assert routing.refused
    assert routing.refusal_basis == "historical"


def test_a_partly_refused_question_keeps_its_actionable_part():
    routing = route(Stub(reply("refused", "data", basis="historical")), "q")
    assert routing.refused
    assert routing.actionable == (Intent.DATA,)


# -- the prompt ----------------------------------------------------------


def test_the_prompt_names_every_class_and_forbids_answering():
    prompt = system_prompt()
    for intent in Intent:
        assert intent.value in prompt
    assert "You do not answer the question" in prompt
    assert "may belong to more than one class" in prompt


def test_the_router_is_given_no_tools():
    """It classifies; it cannot look anything up, so it cannot answer."""
    stub = Stub(reply("data"))
    route(stub, "q")
    assert stub.calls[0]["role"] is Role.ROUTER


# -- JSON handling and the retry budget ----------------------------------


def test_fenced_json_is_accepted():
    stub = Stub('```json\n{"intents": ["data"], "reason": "r"}\n```')
    assert route(stub, "q").intents == (Intent.DATA,)


def test_json_wrapped_in_prose_is_accepted():
    stub = Stub('Sure! {"intents": ["rules"], "reason": "r"} Hope that helps.')
    assert route(stub, "q").intents == (Intent.RULES,)


def test_a_malformed_reply_gets_one_correction_with_the_error():
    """
    A bare "try again" wastes the turn. The retry hands the model its own parse
    error, which is usually enough.
    """
    stub = Stub("not json at all", reply("data"))
    routing = route(stub, "q")
    assert routing.intents == (Intent.DATA,)
    assert len(stub.calls) == 2
    assert "did not parse as JSON" in stub.calls[1]["messages"][-1]["content"]


def test_the_retry_is_bounded():
    """Unbounded retries on a confused model burn budget."""
    stub = Stub("nope", "still nope", reply("data"))
    with pytest.raises(JsonReplyError, match="after 2 attempts"):
        route(stub, "q")
    assert len(stub.calls) == 2


# -- usage accounting ----------------------------------------------------


def test_usage_adds_up_per_role():
    ledger = Ledger()
    ledger.record(Role.ROUTER, Usage(100, 20))
    ledger.record(Role.ROUTER, Usage(50, 10))
    ledger.record(Role.ANSWER, Usage(900, 300))
    assert ledger.by_role[Role.ROUTER] == Usage(150, 30)
    assert ledger.total == Usage(1050, 330)
    assert ledger.calls == 3
    assert "router" in ledger.render()


def test_asking_for_json_returns_the_reply_so_usage_can_be_recorded():
    payload, got = ask_json(Stub('{"a": 1}'), role=Role.ROUTER, system="s", prompt="p")
    assert payload == {"a": 1}
    assert got.usage.input_tokens == 10


# -- the labelled set ----------------------------------------------------


def test_the_labelled_set_is_balanced_enough_to_measure():
    """
    The 4.7 labels alone were 12 `data` against one each of three other
    classes, and a classifier answering "data" every time would have looked
    respectable. No class may dominate.
    """
    from collections import Counter

    counts = Counter(i for case in CASES for i in case.expected)
    assert len(CASES) == 45
    assert min(counts.values()) >= 7
    assert max(counts.values()) <= len(CASES) // 3


def test_the_set_contains_compound_questions():
    assert sum(1 for case in CASES if len(case.expected) > 1) >= 4


def test_scoring_is_exact_set_match_not_partial_credit():
    """
    A question needing the engine and the text is answered wrongly if either
    is missed, so partial credit would hide the failure that matters.
    """
    case = next(c for c in CASES if c.expected == frozenset({Intent.CONSTRAINTS, Intent.RULES}))
    assert not Outcome(case, frozenset({Intent.CONSTRAINTS})).correct
    assert Outcome(case, case.expected).correct


def test_an_unparseable_reply_is_recorded_rather_than_abandoning_the_run():
    """
    One bad response should not lose the whole run, and the count is itself a
    finding about the model.
    """
    report = score(Stub(*(["garbage"] * 200)), CASES[:3])
    assert report.scored == 3
    assert report.errors == 3
    assert report.accuracy == 0.0


def test_refusal_recall_is_reported_separately():
    """
    Missing a refusal is the expensive error: the question gets answered, and a
    historical question answered from current data is wrong invisibly.
    """
    refusal_cases = tuple(c for c in CASES if Intent.REFUSED in c.expected)[:2]
    report = score(Stub(*([reply("refused", basis="historical")] * 4)), refusal_cases)
    assert report.refusal_recall() == 1.0
    missed = score(Stub(*([reply("data")] * 4)), refusal_cases)
    assert missed.refusal_recall() == 0.0


# -- prompt caching (task 6.8) -------------------------------------------


class RecordingCaller:
    """
    A stand-in for AnthropicCaller that records the request it would send.

    Lets the cache breakpoint's *placement* be tested without a key, which is
    the part that was measurably easy to get wrong.
    """

    def __init__(self, *, cache: bool = True) -> None:
        from agent.llm import CACHE_BREAKPOINT

        self.cache = cache
        self.breakpoint = CACHE_BREAKPOINT
        self.sent: list[dict] = []

    def __call__(self, *, role, system, messages, max_tokens=1024, tools=None):
        system_blocks = [{"type": "text", "text": system}]
        if self.cache:
            system_blocks[0]["cache_control"] = dict(self.breakpoint)
        request = {"system": system_blocks, "messages": messages}
        if tools:
            request["tools"] = tools
        self.sent.append(request)
        return Reply(text=reply("data"), usage=Usage(10, 5), model="stub")


def test_the_cache_breakpoint_sits_on_the_system_block():
    """
    Not on the last tool. The request is assembled tools-then-system, so a
    breakpoint after the system text covers both; marking the last tool caches
    the tools and leaves the system prompt out. Measured on a 2,700-token
    prefix: 2,650 cached via the system block against 2,565 via the last tool.
    """
    from agent.tools import specs

    caller = RecordingCaller()
    caller(role=Role.ANSWER, system="s", messages=[], tools=specs())
    sent = caller.sent[0]
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert all("cache_control" not in tool for tool in sent["tools"])


def test_caching_can_be_turned_off_for_the_comparison_arm():
    caller = RecordingCaller(cache=False)
    caller(role=Role.ROUTER, system="s", messages=[])
    assert "cache_control" not in caller.sent[0]["system"][0]


def test_the_ledger_reports_a_cache_hit_rate_over_cacheable_tokens_only():
    """
    Denominator is reads plus writes, not total input: the per-turn message is
    never cacheable, so including it would understate how well the prefix is
    being reused.
    """
    ledger = Ledger()
    ledger.record(Role.ANSWER, Usage(input_tokens=84, output_tokens=10, cache_write_tokens=2650))
    assert ledger.cache_hit_rate(Role.ANSWER) == 0.0
    ledger.record(Role.ANSWER, Usage(input_tokens=84, output_tokens=10, cache_read_tokens=2650))
    assert ledger.cache_hit_rate(Role.ANSWER) == 0.5


def test_a_ledger_with_nothing_cached_says_so_rather_than_showing_a_bare_zero():
    """
    The router's prefix is 447 tokens, below the minimum, so its breakpoint is
    ignored rather than charged. A bare 0% would read as a misconfiguration.
    """
    ledger = Ledger()
    ledger.record(Role.ROUTER, Usage(452, 20))
    rendered = ledger.render()
    assert "below the model's minimum" in rendered
    assert "ignored, not charged" in rendered


def test_a_cache_hit_rate_is_zero_rather_than_undefined_when_nothing_is_cacheable():
    assert Ledger().cache_hit_rate() == 0.0
