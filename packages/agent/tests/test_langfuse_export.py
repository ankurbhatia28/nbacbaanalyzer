"""
The Langfuse exporter (D16), tested against a fake client.

**Not verified against the live service here.** What these tests cover is the
mapping from our recorded tree onto Langfuse's, and -- far more importantly --
that every way this can fail returns False instead of raising. 6.13 settles
that tracing degrades while spend refuses, and an exporter that throws would
break that promise.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field

import pytest

from agent.langfuse_export import ENV_KEYS, LangfuseExporter, configured
from agent.trace import Exporter, Kind, Trace


@dataclass
class FakeObservation:
    name: str
    as_type: str
    model: str | None = None
    depth: int = 0
    updates: list[dict] = field(default_factory=list)

    events: list[dict] = field(default_factory=list)

    def update(self, **kwargs) -> None:
        self.updates.append(kwargs)

    def create_event(self, **kwargs) -> None:
        self.events.append(kwargs)


@dataclass
class FakeClient:
    """Records what the adapter asked for, in order, including nesting depth."""

    observations: list[FakeObservation] = field(default_factory=list)
    scores: list[dict] = field(default_factory=list)
    flushes: int = 0
    explode_on: str | None = None
    _depth: int = 0

    events: list[dict] = field(default_factory=list)

    @contextmanager
    def start_as_current_observation(self, *, as_type, name, **kwargs):
        if self.explode_on and self.explode_on in name:
            raise RuntimeError("langfuse is having a day")
        observation = FakeObservation(
            name=name, as_type=as_type, model=kwargs.get("model"), depth=self._depth
        )
        self.observations.append(observation)
        self._depth += 1
        try:
            yield observation
        finally:
            self._depth -= 1

    def score_current_trace(self, **kwargs) -> None:
        self.scores.append(kwargs)

    def flush(self) -> None:
        self.flushes += 1


def built() -> Trace:
    """One agent run, with a tool beside the generation that requested it."""
    trace = Trace(session="conversation-1", environment="development", tags=["rules"])
    root = trace.begin("What is the Standard Traded Player Exception?")
    generation = root.child(Kind.GENERATION, "generate-answer")
    generation.end(
        output="It permits replacing one traded player.",
        model="claude-sonnet-5",
        usage={"input": 120, "output": 40, "cache_read_input_tokens": 2650},
    )
    root.child(Kind.RETRIEVER, "fetch-provision", input={"citation": "Art. VII §8"}).end(
        output={"citation_returned": "Art. VII §8"}
    )
    root.end(output="It permits replacing one traded player.")
    trace.metadata["rounds"] = 2
    trace.scores = {"supported": 1, "trustworthy": 1}
    return trace


def wired(**kwargs) -> tuple[LangfuseExporter, FakeClient]:
    client = FakeClient()
    exporter = LangfuseExporter(**kwargs)
    exporter._client = client
    return exporter, client


# -- the mapping ----------------------------------------------------------


def test_the_root_is_an_agent_named_for_what_it_does():
    exporter, client = wired()
    assert exporter.export(built())
    root = client.observations[0]
    assert root.as_type == "agent"
    assert root.name == "answer-cba-question"
    assert root.depth == 0


def test_the_tree_is_replayed_with_children_nested_under_the_root():
    """
    Not a flat list. A tool call has to show which step it belongs to, so the
    recorded shape is reproduced rather than flattened.
    """
    exporter, client = wired()
    exporter.export(built())
    assert [(o.name, o.depth) for o in client.observations] == [
        ("answer-cba-question", 0),
        ("generate-answer", 1),
        ("fetch-provision", 1),
    ]


def test_a_model_call_is_sent_as_a_generation_with_its_model():
    """
    A generation carries a model and token counts, which is what makes the cost
    view work. A plain span would not.
    """
    exporter, client = wired()
    exporter.export(built())
    generation = next(o for o in client.observations if o.as_type == "generation")
    assert generation.name == "generate-answer"
    assert generation.model == "claude-sonnet-5"


def test_a_tool_is_sent_as_a_retriever_rather_than_a_generic_span():
    """
    The specific type, because every tool here looks something up without
    changing state -- ADR-004 showing through.
    """
    exporter, client = wired()
    exporter.export(built())
    assert any(o.as_type == "retriever" for o in client.observations)
    assert not any(o.as_type == "span" for o in client.observations)


def test_token_counts_are_reported_with_cache_reads_kept_separate():
    """
    At a 97% cache hit rate, folding cache reads into input would misstate the
    bill badly -- the one number a cost dashboard exists to get right.
    """
    exporter, client = wired()
    exporter.export(built())
    generation = next(o for o in client.observations if o.as_type == "generation")
    assert generation.updates[0]["usage_details"] == {
        "input": 120,
        "output": 40,
        "cache_read_input_tokens": 2650,
    }


def test_trace_attributes_are_propagated_with_the_v4_api(monkeypatch):
    """
    v4 has no `update_current_trace`; trace-level attributes are set with the
    module-level `propagate_attributes`, and it must wrap the root's creation
    because it only applies to spans created after it.
    """
    captured: dict = {}

    from contextlib import contextmanager

    import langfuse

    @contextmanager
    def fake_propagate(**kwargs):
        captured.update(kwargs)
        yield

    monkeypatch.setattr(langfuse, "propagate_attributes", fake_propagate)
    exporter, _ = wired()
    exporter.export(built())
    assert captured["session_id"] == "conversation-1"
    assert captured["tags"] == ["rules"]
    assert captured["environment"] == "development"
    assert captured["trace_name"] == "answer-cba-question"


def test_the_root_carries_the_trace_input_and_output():
    """`set_trace_io` is deprecated in v4; the root observation supplies both."""
    exporter, client = wired()
    exporter.export(built())
    root = client.observations[0]
    assert root.updates[-1]["output"].startswith("It permits")


def test_judgements_are_sent_as_scores_not_tags():
    """
    Tags are immutable and set at creation; whether an answer was supported is
    only known once it exists. Scores are the documented place for that.
    """
    exporter, client = wired()
    exporter.export(built())
    assert {s["name"]: s["value"] for s in client.scores} == {
        "supported": 1,
        "trustworthy": 1,
    }


def test_a_failed_span_is_marked_as_an_error():
    trace = Trace()
    trace.begin("q").child(Kind.GENERATION, "generate-answer").end(error="RuntimeError: boom")
    exporter, client = wired()
    exporter.export(trace)
    observation = client.observations[-1]
    assert observation.updates[0]["level"] == "ERROR"
    assert "boom" in observation.updates[0]["status_message"]


def test_it_flushes_because_a_request_may_outlive_the_process():
    exporter, client = wired()
    exporter.export(built())
    assert client.flushes == 1


def test_flushing_can_be_deferred_for_a_batch():
    exporter, client = wired(flush_each=False)
    exporter.export(built())
    assert client.flushes == 0


def test_an_empty_trace_is_a_no_op_rather_than_an_error():
    exporter, client = wired()
    assert exporter.export(Trace())
    assert client.observations == []


# -- every failure degrades, none raises ---------------------------------


def test_a_missing_key_is_reported_rather_than_raised(monkeypatch):
    for name in ENV_KEYS:
        monkeypatch.delenv(name, raising=False)
    assert not configured()
    exporter = LangfuseExporter()
    assert exporter.export(built()) is False
    assert exporter.failed == 1
    assert "not set" in (exporter.last_error or "")


def test_a_missing_key_is_only_diagnosed_once(monkeypatch):
    """Not once per request, which would be noise on every single answer."""
    for name in ENV_KEYS:
        monkeypatch.delenv(name, raising=False)
    exporter = LangfuseExporter()
    for _ in range(3):
        exporter.export(built())
    assert exporter.failed == 3
    assert exporter._unavailable


def test_an_sdk_that_throws_mid_export_does_not_raise():
    """
    A network failure, a bad key, or an SDK whose shape has moved since this
    adapter was written. 6.13: tracing degrades, spend refuses.
    """
    exporter, client = wired()
    client.explode_on = "generate-answer"
    assert exporter.export(built()) is False
    assert "having a day" in (exporter.last_error or "")


def test_a_failure_does_not_count_as_exported():
    exporter, client = wired()
    client.explode_on = "answer-cba-question"
    exporter.export(built())
    assert exporter.exported == 0


def test_a_failing_score_does_not_fail_the_export():
    """A score is the least important thing in the trace."""

    class NoScores(FakeClient):
        def score_current_trace(self, **kwargs):
            raise RuntimeError("scores are down")

    exporter = LangfuseExporter()
    exporter._client = NoScores()
    assert exporter.export(built()) is True
    assert "scores are down" in (exporter.last_error or "")


def test_it_satisfies_the_exporter_protocol():
    assert isinstance(LangfuseExporter(), Exporter)


def test_importing_the_module_needs_neither_the_sdk_nor_a_key():
    assert LangfuseExporter()._client is None


@pytest.mark.parametrize("missing", ENV_KEYS)
def test_one_key_alone_is_not_configured(monkeypatch, missing):
    for name in ENV_KEYS:
        monkeypatch.setenv(name, "x")
    monkeypatch.delenv(missing)
    assert not configured()


def test_an_event_is_created_on_its_parent_not_opened_as_an_observation():
    """
    `event` is not a valid `as_type`: the SDK warns and silently downgrades it
    to a span. Events belong on their parent, which also fits what they are --
    instants with no duration and no children.
    """
    trace = Trace()
    root = trace.begin("q")
    root.child(Kind.EVENT, "refuse-question", output="declined").end()
    root.end(output="declined")
    exporter, client = wired()
    exporter.export(trace)
    assert [o.as_type for o in client.observations] == ["agent"]
    assert client.observations[0].events[0]["name"] == "refuse-question"


def test_only_short_stable_dimensions_are_propagated(monkeypatch):
    """
    Propagated attribute values are capped at 200 characters and dropped with a
    warning above it -- a citation list blew through that. Per-run detail goes
    on the root observation's metadata, where it describes this run rather than
    every span in it.
    """
    captured: dict = {}

    from contextlib import contextmanager

    import langfuse

    @contextmanager
    def fake_propagate(**kwargs):
        captured.update(kwargs)
        yield

    monkeypatch.setattr(langfuse, "propagate_attributes", fake_propagate)
    trace = built()
    trace.metadata["citations"] = ["Art. VII §6(j)(1)(i)"] * 40
    exporter, client = wired()
    exporter.export(trace)
    assert "metadata" not in captured
    assert client.observations[0].name == "answer-cba-question"
