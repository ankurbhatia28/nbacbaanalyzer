"""
The Langfuse exporter (D16), tested against a fake client.

**Not verified against the live service.** No Langfuse keys exist in this repo
yet, so what is tested here is the contract: the mapping from our trace shape
onto theirs, and -- far more importantly -- that every way this can fail
returns False instead of raising. 6.13 settles that tracing degrades while
spend refuses, and an exporter that throws would break that promise.

The live check is one command once keys are set; until then this file is honest
about what it does and does not cover.
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
    updates: list[dict] = field(default_factory=list)

    def update(self, **kwargs) -> None:
        self.updates.append(kwargs)


@dataclass
class FakeClient:
    """Records what the adapter asked for, in order."""

    observations: list[FakeObservation] = field(default_factory=list)
    flushes: int = 0
    explode_on: str | None = None

    @contextmanager
    def start_as_current_observation(self, *, as_type, name, **kwargs):
        if self.explode_on and self.explode_on in name:
            raise RuntimeError("langfuse is having a day")
        observation = FakeObservation(name=name, as_type=as_type, model=kwargs.get("model"))
        self.observations.append(observation)
        yield observation

    def flush(self) -> None:
        self.flushes += 1


def built() -> Trace:
    trace = Trace(session="demo")
    trace.metadata["trustworthy"] = True
    trace.record(Kind.USER_TURN, "question", text="q")
    model = trace.start(Kind.MODEL_CALL, "answer")
    model.ended_at = model.started_at + 2.0
    model.payload.update(
        model="claude-sonnet-5", input_tokens=120, output_tokens=40, cached_tokens=2650
    )
    trace.record(Kind.TOOL_CALL, "fetch_provision", citation="Art. VII §8", ok=True)
    trace.record(Kind.ANSWER, "final", chars=200)
    return trace


def wired(**kwargs) -> tuple[LangfuseExporter, FakeClient]:
    client = FakeClient()
    exporter = LangfuseExporter(**kwargs)
    exporter._client = client
    return exporter, client


# -- the mapping ----------------------------------------------------------


def test_a_session_becomes_one_root_with_each_span_beneath_it():
    exporter, client = wired()
    assert exporter.export(built())
    assert client.observations[0].name == "demo"
    assert client.observations[0].as_type == "span"
    assert len(client.observations) == 5, "one root plus four spans"


def test_a_model_call_is_sent_as_a_generation_with_its_model():
    """
    A generation carries a model and token counts, which is what makes the
    cost view work. A plain span would not.
    """
    exporter, client = wired()
    exporter.export(built())
    generation = next(o for o in client.observations if o.as_type == "generation")
    assert generation.name == "model_call:answer"
    assert generation.model == "claude-sonnet-5"


def test_everything_other_than_a_model_call_is_a_plain_span():
    exporter, client = wired()
    exporter.export(built())
    types = {o.name: o.as_type for o in client.observations}
    assert types["tool_call:fetch_provision"] == "span"
    assert types["user_turn:question"] == "span"
    assert types["answer:final"] == "span"


def test_token_counts_are_reported_with_cache_reads_kept_separate():
    """
    At a 97% cache hit rate, folding cache reads into input would misstate the
    bill badly -- which is the one number a cost dashboard exists to get right.
    """
    exporter, client = wired()
    exporter.export(built())
    generation = next(o for o in client.observations if o.as_type == "generation")
    usage = generation.updates[0]["usage_details"]
    assert usage == {"input": 120, "output": 40, "cache_read_input_tokens": 2650}


def test_span_payload_travels_as_metadata():
    exporter, client = wired()
    exporter.export(built())
    tool = next(o for o in client.observations if o.name == "tool_call:fetch_provision")
    assert tool.updates[0]["metadata"]["citation"] == "Art. VII §8"


def test_the_model_is_not_duplicated_into_metadata():
    exporter, client = wired()
    exporter.export(built())
    generation = next(o for o in client.observations if o.as_type == "generation")
    assert "model" not in generation.updates[0]["metadata"]


def test_a_failed_span_is_marked_as_an_error():
    trace = Trace(session="s")
    span = trace.start(Kind.MODEL_CALL, "answer")
    span.error = "RuntimeError: boom"
    exporter, client = wired()
    exporter.export(trace)
    observation = client.observations[-1]
    assert observation.updates[0]["level"] == "ERROR"
    assert "boom" in observation.updates[0]["status_message"]


def test_trace_metadata_reaches_the_root():
    exporter, client = wired()
    exporter.export(built())
    assert client.observations[0].updates[-1]["output"]["events"] == 4


def test_it_flushes_because_a_request_may_outlive_the_process():
    exporter, client = wired()
    exporter.export(built())
    assert client.flushes == 1


def test_flushing_can_be_deferred_for_a_batch():
    exporter, client = wired(flush_each=False)
    exporter.export(built())
    assert client.flushes == 0


# -- every failure degrades, none raises ---------------------------------


def test_a_missing_key_is_reported_rather_than_raised(monkeypatch):
    """
    The common case on a fresh checkout, and it must not be a crash.
    """
    for name in ENV_KEYS:
        monkeypatch.delenv(name, raising=False)
    assert not configured()
    exporter = LangfuseExporter()
    assert exporter.export(built()) is False
    assert exporter.failed == 1
    assert exporter.last_error is not None
    assert "not set" in exporter.last_error


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
    client.explode_on = "model_call"
    assert exporter.export(built()) is False
    assert exporter.failed == 1
    assert "having a day" in (exporter.last_error or "")


def test_a_failure_does_not_count_as_exported():
    exporter, client = wired()
    client.explode_on = "demo"
    exporter.export(built())
    assert exporter.exported == 0


def test_it_satisfies_the_exporter_protocol():
    """So it is interchangeable with the file and null exporters."""
    assert isinstance(LangfuseExporter(), Exporter)


def test_importing_the_module_needs_neither_the_sdk_nor_a_key():
    """
    Which is what lets the whole suite import it unconditionally. The client is
    built lazily on first export.
    """
    exporter = LangfuseExporter()
    assert exporter._client is None


@pytest.mark.parametrize("missing", ENV_KEYS)
def test_one_key_alone_is_not_configured(monkeypatch, missing):
    for name in ENV_KEYS:
        monkeypatch.setenv(name, "x")
    monkeypatch.delenv(missing)
    assert not configured()
