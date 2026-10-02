"""
Tracing (tasks 6.10, 6.10a), tested without a vendor.

The shape D4 asks for is the same whoever stores it, so the model is tested
here and the vendor is a thin adapter. What matters: a backend being down, out
of quota or rate limited must never fail a user's question.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.trace import (
    CappedExporter,
    Exporter,
    FileExporter,
    Kind,
    NullExporter,
    Trace,
    summarise,
)


def built() -> Trace:
    trace = Trace(session="s")
    trace.record(Kind.USER_TURN, "question", text="q")
    span = trace.start(Kind.MODEL_CALL, "router")
    span.ended_at = span.started_at + 1.25
    trace.record(Kind.TOOL_CALL, "fetch_provision", citation="Art. VII §8")
    trace.record(Kind.ANSWER, "final", chars=120)
    return trace


# -- the shape D4 asks for ------------------------------------------------


def test_a_trace_covers_the_session_not_a_single_call():
    """
    D4: one trace per user session. A conversation is the unit a reader wants
    to follow, and splitting it per turn loses what makes a trace useful.
    """
    trace = built()
    kinds = [s.kind for s in trace.spans]
    assert Kind.USER_TURN in kinds
    assert Kind.MODEL_CALL in kinds
    assert Kind.TOOL_CALL in kinds
    assert Kind.ANSWER in kinds
    assert trace.session == "s"


def test_events_are_the_span_count_so_a_cap_can_trust_it():
    """
    The budget reasons about events and the trace about spans; conflating the
    words is how an event cap drifts out of step with what is actually sent.
    """
    assert built().events == 4


def test_a_span_records_its_duration():
    trace = built()
    model = next(s for s in trace.spans if s.kind is Kind.MODEL_CALL)
    assert model.seconds == pytest.approx(1.25)


def test_an_unfinished_span_reports_zero_rather_than_failing():
    trace = Trace()
    span = trace.start(Kind.MODEL_CALL, "answer")
    assert span.ended_at is None
    assert span.seconds == 0.0
    assert span.to_json()["seconds"] == 0.0


def test_a_trace_serialises_to_one_json_object():
    payload = built().to_json()
    assert set(payload) == {
        "trace_id",
        "session",
        "started_at",
        "events",
        "metadata",
        "spans",
    }
    assert json.loads(json.dumps(payload, default=str))


def test_a_span_error_is_kept_and_a_clean_span_carries_no_error_key():
    trace = Trace()
    bad = trace.start(Kind.MODEL_CALL, "answer")
    bad.error = "RuntimeError: boom"
    assert bad.to_json()["error"] == "RuntimeError: boom"
    good = trace.record(Kind.ANSWER, "final")
    assert "error" not in good.to_json()


# -- exporters must never fail a question --------------------------------


def test_the_default_exporter_drops_so_tracing_is_opt_in():
    exporter = NullExporter()
    assert exporter.export(built()) is False
    assert exporter.dropped == 1


def test_the_file_exporter_appends_one_line_per_trace(tmp_path):
    path = tmp_path / "nested" / "traces.jsonl"
    exporter = FileExporter(path)
    assert exporter.export(built())
    assert exporter.export(built())
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["events"] == 4


def test_an_unwritable_path_returns_false_rather_than_raising(tmp_path):
    """A full disk should not fail a user's question."""
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    exporter = FileExporter(blocker / "traces.jsonl")
    assert exporter.export(built()) is False


def test_exporters_satisfy_the_protocol():
    for exporter in (
        NullExporter(),
        FileExporter(Path("/tmp/x.jsonl")),
        CappedExporter(NullExporter(), 10),
    ):
        assert isinstance(exporter, Exporter)


# -- the event cap (6.13 applied to tracing) -----------------------------


def test_the_cap_drops_a_trace_that_would_exceed_the_allowance(tmp_path):
    exporter = CappedExporter(FileExporter(tmp_path / "t.jsonl"), max_events=6)
    assert exporter.export(built())  # 4 events
    assert not exporter.export(built())  # would make 8
    assert exporter.dropped_traces == 1
    assert exporter.dropped_events == 4
    assert exporter.remaining == 2


def test_a_dropped_trace_does_not_consume_the_allowance(tmp_path):
    exporter = CappedExporter(FileExporter(tmp_path / "t.jsonl"), max_events=5)
    exporter.export(built())
    exporter.export(built())
    assert exporter.spent == 4, "the dropped trace must not be billed"


def test_the_cap_reports_that_questions_were_still_answered(tmp_path):
    exporter = CappedExporter(FileExporter(tmp_path / "t.jsonl"), max_events=1)
    exporter.export(built())
    assert "the questions were still answered" in exporter.render()


def test_a_failing_inner_exporter_does_not_consume_the_allowance():
    exporter = CappedExporter(NullExporter(), max_events=100)
    assert not exporter.export(built())
    assert exporter.spent == 0, "nothing was stored, so nothing should be billed"


# -- the loop produces one ------------------------------------------------


def test_the_summary_is_readable():
    text = summarise(built())
    assert "4 events" in text
    assert "model_call 1" in text
    assert "tool_call 1" in text
