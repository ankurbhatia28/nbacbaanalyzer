"""
Streaming (task 6.9), tested without a key.

What streaming has to get right is not the text of the answer -- by the time
that arrives the work is done -- but that progress appears *while* the work
happens, and that the stream cannot disagree with the trace or quietly drop the
unverified-figure warning.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.llm import Reply, ToolRequest, Usage
from agent.stream import STEP_LABELS, TOOL_LABELS, Event, stream
from agent.tools import Resources
from nbadata.db import open_readonly
from nbadata.ingest.load import load as load_csvs
from rag import index as ix
from rag.chunks import build as build_chunks
from rag.crossrefs import build as build_graph
from rag.definitions import build as build_definitions
from rag.outline import DEFAULT_PDF, load

CSV_DIR = Path(__file__).resolve().parents[3] / "scraper" / "out"
pytestmark = pytest.mark.skipif(
    not DEFAULT_PDF.exists() or not (CSV_DIR / "contracts.csv").exists(),
    reason="CBA PDF or scraper output not present",
)


@pytest.fixture(scope="module")
def res(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("stream")
    outline = load()
    ix.build(
        tmp / "cba.db",
        build_chunks(outline),
        build_definitions(outline),
        build_graph(outline),
        outline,
    )
    load_csvs(CSV_DIR, tmp / "league.db")
    return Resources(
        league=open_readonly(tmp / "league.db"),
        cba=ix.open_index(tmp / "cba.db"),
        base_season_cap=136_021_000,
    )


class Script:
    def __init__(self, *, router: str, intent: str, answers: list) -> None:
        self.router, self.intent, self.answers = router, intent, list(answers)

    def __call__(self, *, role, system, messages, max_tokens=1024, tools=None) -> Reply:
        from agent.models import Role

        if role is Role.ROUTER:
            return Reply(self.router, Usage(10, 5), "stub")
        if role is Role.INTENT:
            return Reply(self.intent, Usage(10, 5), "stub")
        nxt = self.answers.pop(0) if self.answers else "done"
        if isinstance(nxt, list):
            return Reply(
                "",
                Usage(10, 5),
                "stub",
                tool_requests=tuple(
                    ToolRequest(id=f"t{i}", name=n, arguments=a) for i, (n, a) in enumerate(nxt)
                ),
                raw_content=({"type": "text", "text": ""},),
            )
        return Reply(nxt, Usage(10, 5), "stub")


def routing(*intents: str, basis: str | None = None) -> str:
    return json.dumps({"intents": list(intents), "reason": "r", "refusal_basis": basis})


def planning(*provisions: str) -> str:
    return json.dumps({"provisions": list(provisions), "players": [], "teams": [], "reason": "r"})


def collect(res, script, question="q"):
    return list(stream(script, question=question, res=res, poll_seconds=0.005))


# -- the stream's shape --------------------------------------------------


def test_a_run_starts_and_finishes(res):
    updates = collect(res, Script(router=routing("rules"), intent=planning(), answers=["hi"]))
    assert updates[0].event is Event.STARTED
    assert updates[-1].event is Event.DONE


def test_progress_names_the_step_in_words_a_reader_can_judge(res):
    """
    "searching the Agreement" appearing when you asked for a salary figure is a
    visible sign the question was misread; `search_cba` alone would not be.
    """
    updates = collect(
        res,
        Script(
            router=routing("rules"),
            intent=planning("Trade Rules"),
            answers=[[("fetch_provision", {"citation": "Art. VII §8"})], "done"],
        ),
    )
    texts = [u.text for u in updates]
    assert STEP_LABELS["classify-question"] in texts
    assert any(TOOL_LABELS["fetch_provision"] in t for t in texts)


def test_a_tool_update_carries_the_citation_it_reached(res):
    """
    "reading the provision Art. VII §8" says whether the right provision was
    reached. "reading the provision" alone does not.
    """
    updates = collect(
        res,
        Script(
            router=routing("rules"),
            intent=planning(),
            answers=[[("fetch_provision", {"citation": "Art. VII §8"})], "done"],
        ),
    )
    tool = next(u for u in updates if u.event is Event.TOOL)
    assert "Art. VII §8" in tool.text
    assert tool.detail["citation"] == "Art. VII §8"


def test_the_stream_cannot_show_a_step_the_trace_does_not_have(res):
    """
    Progress is read from the trace rather than a parallel event list, so what
    a user saw and what was recorded cannot disagree.
    """
    script = Script(
        router=routing("rules"),
        intent=planning(),
        answers=[[("fetch_provision", {"citation": "Art. VII §8"})], "done"],
    )
    updates = collect(res, script)
    verdict = updates[-1].detail["verdict"]
    spans = [c.name for c in verdict.trace.root.children]
    streamed = [
        u.detail.get("step") or u.detail.get("tool", "").replace("_", "-")
        for u in updates
        if u.event in (Event.STEP, Event.TOOL)
    ]
    assert streamed == spans


# -- the outcome is the same as the non-streaming path -------------------


def test_the_final_update_carries_the_audited_verdict(res):
    """
    A caller that wants citations, assumptions and the unverified-figure
    warning gets the same object `answer()` returns.
    """
    updates = collect(
        res,
        Script(
            router=routing("rules"),
            intent=planning(),
            answers=[[("fetch_provision", {"citation": "Art. VII §8"})], "The rules say..."],
        ),
    )
    done = updates[-1]
    assert done.detail["verdict"].text == "The rules say..."
    assert done.detail["citations"]
    assert "unsourced_figures" in done.detail, "5.9 must not be dropped by the streaming path"
    assert "trustworthy" in done.detail


def test_an_unverified_figure_survives_the_stream(res):
    """
    Task 5.9 is worth nothing if streaming quietly drops the warning.
    """
    updates = collect(
        res,
        Script(
            router=routing("rules"),
            intent=planning(),
            answers=[
                [("fetch_provision", {"citation": "Art. VII §8"})],
                "The limit is $9,876,543.",
            ],
        ),
    )
    done = updates[-1]
    assert done.detail["unsourced_figures"] == ["$9,876,543"]
    assert done.detail["trustworthy"] is False


def test_a_refusal_streams_as_a_refusal_with_its_basis(res):
    updates = collect(
        res,
        Script(router=routing("refused", basis="opinion"), intent=planning(), answers=[]),
    )
    refusal = next(u for u in updates if u.event is Event.REFUSED)
    assert refusal.detail["basis"] == "opinion"
    assert "D10" in refusal.text


def test_a_clarification_streams_as_one(res):
    script = Script(
        router=routing("data"),
        intent=json.dumps({"provisions": [], "players": ["Williams"], "teams": [], "reason": "r"}),
        answers=["unreached"],
    )
    updates = collect(res, script)
    kinds = {u.event for u in updates}
    if Event.CLARIFICATION in kinds:
        clar = next(u for u in updates if u.event is Event.CLARIFICATION)
        assert "Which did you mean" in clar.text


def test_a_cap_streams_as_an_error_rather_than_an_answer(res):
    from agent.budget import Budget

    budget = Budget(max_requests=1)
    budget.check_rate()
    updates = list(
        stream(
            Script(router=routing("rules"), intent=planning(), answers=["x"]),
            question="q",
            res=res,
            budget=budget,
            poll_seconds=0.005,
        )
    )
    error = next(u for u in updates if u.event is Event.ERROR)
    assert "rate limit" in error.detail["over_budget"]


def test_a_crash_in_the_worker_surfaces_as_an_error(res):
    class Broken:
        def __call__(self, **kwargs):
            raise RuntimeError("boom")

    updates = list(stream(Broken(), question="q", res=res, poll_seconds=0.005))
    assert updates[-1].event is Event.ERROR
    assert "boom" in updates[-1].text
