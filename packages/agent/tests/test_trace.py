"""
Tracing (tasks 6.10, 6.10a), tested without a vendor.

The structure follows Langfuse's "what does a good trace look like?" guidance,
and these tests hold the parts of it that are easy to regress: correct
observation types, nesting rather than a flat list, verb-first names, and
meaningful input and output on the root.
"""

from __future__ import annotations

import json
from pathlib import Path

from agent.trace import (
    CappedExporter,
    Exporter,
    FileExporter,
    Kind,
    NullExporter,
    Trace,
    summarise,
    walk,
)


def built() -> Trace:
    """One agent run: question in, answer out, with a tool beside its generation."""
    trace = Trace(session="conversation-1", environment="development", tags=["rules"])
    root = trace.begin("What is the Standard Traded Player Exception?")
    generation = root.child(Kind.GENERATION, "generate-answer", input=[{"role": "user"}])
    generation.end(
        output="It permits replacing one traded player.",
        model="claude-sonnet-5",
        usage={"input": 120, "output": 40, "cache_read_input_tokens": 2650},
    )
    root.child(Kind.RETRIEVER, "fetch-provision", input={"citation": "Art. VII §8"}).end(
        output={"citation_returned": "Art. VII §8"}
    )
    root.end(output="It permits replacing one traded player.")
    trace.scores = {"supported": 1, "trustworthy": 1}
    return trace


# -- the shape the guidance asks for -------------------------------------


def test_a_trace_is_one_agent_run_with_the_question_in_and_the_answer_out():
    """
    The trace list shows the root's input and output, so they are what a
    reviewer reads first -- the user's question and the assistant's answer,
    not a JSON blob of arguments.
    """
    trace = built()
    assert trace.root is not None
    assert trace.root.kind is Kind.AGENT
    assert trace.root.input.startswith("What is")
    assert trace.root.output.startswith("It permits")


def test_a_tool_is_a_sibling_of_the_generation_not_a_child_of_it():
    """
    The guidance is explicit: a tool call nests under the agent that
    orchestrates the step, as a sibling of the generation that requested it,
    rather than dangling at the trace root or hiding inside the generation.
    """
    trace = built()
    assert trace.root is not None
    kinds = [c.kind for c in trace.root.children]
    assert kinds == [Kind.GENERATION, Kind.RETRIEVER]
    generation = trace.root.children[0]
    assert generation.children == [], "a tool is not a child of the generation"


def test_tools_are_retrievers_because_nothing_here_changes_state():
    """
    ADR-004 showing through: the database and the index are read-only build
    artifacts, so every tool looks something up. `retriever` is the specific
    type for that; `tool` would be the generic fallback.
    """
    trace = built()
    assert trace.root is not None
    tool = trace.root.children[1]
    assert tool.kind is Kind.RETRIEVER


def test_names_are_verb_first_and_carry_no_run_specific_values():
    """
    Names behave like an API -- evaluators, dashboards and saved filters target
    them -- so they must be stable and low-cardinality. No ids, no model names.
    """
    trace = built()
    assert trace.root is not None
    for span in walk(trace.root):
        assert span.name.islower()
        assert not any(ch.isdigit() for ch in span.name), "no run-specific values"
        assert "claude" not in span.name, "never name a span after the model"
        assert span.name.split("-")[0] in {
            "answer",
            "generate",
            "fetch",
            "classify",
            "select",
            "search",
            "resolve",
            "define",
            "query",
            "lookup",
            "refuse",
        }


def test_a_generation_carries_the_model_and_its_token_usage():
    """Without these Langfuse cannot price the call, which is half the point."""
    trace = built()
    assert trace.root is not None
    generation = trace.root.children[0]
    assert generation.model == "claude-sonnet-5"
    assert generation.usage["input"] == 120
    assert generation.usage["cache_read_input_tokens"] == 2650, (
        "cache reads stay separate from input: at a 97% hit rate, folding them "
        "together would misstate the bill"
    )


def test_events_count_the_root_and_every_descendant():
    """
    The budget reasons about events and the trace about spans; keeping the
    word separate is how an event cap stays in step with what is sent.
    """
    assert built().events == 3


def test_an_empty_trace_reports_no_events():
    assert Trace().events == 0
    assert Trace().units == 0


def test_units_count_what_langfuse_bills_the_trace_observations_and_scores():
    """
    D16. Langfuse bills "traces ..., observations ... and scores". Counting
    observations alone -- Raindrop's model -- missed the trace and its scores.
    """
    trace = built()
    assert trace.units == 1 + trace.events + len(trace.scores) == 6
    assert trace.to_json()["units"] == 6


def test_a_trace_serialises_with_its_tree_intact():
    payload = built().to_json()
    assert payload["root"]["kind"] == "agent"
    assert len(payload["root"]["children"]) == 2
    assert json.loads(json.dumps(payload, default=str))


def test_an_empty_field_is_omitted_rather_than_sent_as_null():
    trace = Trace()
    span = trace.begin("q").child(Kind.EVENT, "refuse-question")
    rendered = span.to_json()
    assert "model" not in rendered
    assert "error" not in rendered
    assert "children" not in rendered


def test_a_span_error_is_kept():
    trace = Trace()
    span = trace.begin("q").child(Kind.GENERATION, "generate-answer")
    span.end(error="RuntimeError: boom")
    assert span.to_json()["error"] == "RuntimeError: boom"


def test_scores_are_separate_from_tags():
    """
    Tags are immutable and set at creation, so they carry what is structural.
    Whether an answer was supported is only known once it exists, which is what
    scores are for.
    """
    trace = built()
    assert trace.tags == ["rules"]
    assert trace.scores["trustworthy"] == 1


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
    assert json.loads(lines[0])["events"] == 3


def test_an_unwritable_path_returns_false_rather_than_raising(tmp_path):
    """A full disk should not fail a user's question."""
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    assert FileExporter(blocker / "traces.jsonl").export(built()) is False


def test_exporters_satisfy_the_protocol():
    for exporter in (
        NullExporter(),
        FileExporter(Path("/tmp/x.jsonl")),
        CappedExporter(NullExporter(), 10),
    ):
        assert isinstance(exporter, Exporter)


# -- the event cap -------------------------------------------------------


def test_the_cap_drops_a_trace_that_would_exceed_the_allowance(tmp_path):
    exporter = CappedExporter(FileExporter(tmp_path / "t.jsonl"), max_units=8)
    assert exporter.export(built())  # 6 units
    assert not exporter.export(built())  # would make 12
    assert exporter.dropped_traces == 1
    assert exporter.remaining == 2


def test_a_dropped_trace_does_not_consume_the_allowance(tmp_path):
    exporter = CappedExporter(FileExporter(tmp_path / "t.jsonl"), max_units=8)
    exporter.export(built())
    exporter.export(built())
    assert exporter.spent == 6, "the dropped trace must not be billed"


def test_the_cap_reports_that_questions_were_still_answered(tmp_path):
    exporter = CappedExporter(FileExporter(tmp_path / "t.jsonl"), max_units=1)
    exporter.export(built())
    assert "the questions were still answered" in exporter.render()


def test_a_failing_inner_exporter_does_not_consume_the_allowance():
    exporter = CappedExporter(NullExporter(), max_units=100)
    assert not exporter.export(built())
    assert exporter.spent == 0, "nothing stored, so nothing billed"


def test_the_summary_is_readable():
    text = summarise(built())
    assert "3 events, 6 units" in text
    assert "generation 1" in text
    assert "retriever 1" in text


def test_walking_returns_parents_before_children():
    trace = built()
    assert trace.root is not None
    assert next(s.kind for s in walk(trace.root)) is Kind.AGENT
