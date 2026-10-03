"""
Streaming, with tool-call progress visible (task 6.9).

A question here takes 11 seconds and makes three to eight model calls. Without
streaming the user watches nothing happen for that long, and "nothing happened"
and "it is thinking" look identical.

**What is streamed is progress, not just text.** The tokens of the final answer
matter least: by the time they arrive the work is done. What a user needs while
waiting is *which step is running* -- classifying, choosing provisions, reading
Art. VII §6(j)(1) -- because that is also the first place an answer goes wrong,
and seeing "searching the Agreement" when you asked for a salary figure tells
you immediately that the question was misread.

**The verdict is unchanged.** Streaming is a view of the same run: the loop
still audits its figures, still refuses, still records a trace. An event stream
that could produce a different answer from the non-streaming path would be a
second implementation to keep correct, which is how the two drift apart.

This module turns one `answer()` call into an ordered stream of events. It does
not re-implement the loop; it observes it.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .answer import Verdict, answer
from .budget import Budget
from .llm import Caller
from .tools import Resources
from .trace import Kind, Span, Trace

TOOL_LABELS = {
    "resolve_provision": "looking up the rule by name",
    "fetch_provision": "reading the provision",
    "search_cba": "searching the Agreement",
    "define_term": "checking a defined term",
    "query_league_data": "querying league data",
    "lookup_player": "resolving a player",
}
"""
What each tool is doing, in words a reader can judge.

Named for the *user's* benefit rather than the developer's: "searching the
Agreement" appearing when you asked for a salary figure is a visible sign the
question was misread, which `search_cba` alone would not convey.
"""

STEP_LABELS = {
    "classify-question": "working out what you asked",
    "select-provisions": "choosing which rules apply",
    "generate-answer": "writing the answer",
}


class Event(StrEnum):
    STARTED = "started"
    STEP = "step"
    TOOL = "tool"
    REFUSED = "refused"
    CLARIFICATION = "clarification"
    ANSWER = "answer"
    DONE = "done"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class Update:
    """One thing the caller can show."""

    event: Event
    text: str = ""
    detail: dict[str, Any] = field(default_factory=dict)

    def render(self) -> str:
        return f"[{self.event.value}] {self.text}"


def _label(span: Span) -> Update | None:
    if span.kind is Kind.GENERATION:
        return Update(Event.STEP, STEP_LABELS.get(span.name, span.name), {"step": span.name})
    if span.kind is Kind.RETRIEVER:
        tool = span.name.replace("-", "_")
        detail: dict[str, Any] = {"tool": tool}
        # The citation is the useful part: "reading Art. VII §6(j)(1)" tells a
        # reader whether the right provision was reached, while "reading the
        # provision" alone does not.
        if isinstance(span.input, dict):
            for key in ("citation", "name", "term", "query"):
                if span.input.get(key):
                    detail[key] = span.input[key]
                    break
        text = TOOL_LABELS.get(tool, tool.replace("_", " "))
        if cite := detail.get("citation"):
            text = f"{text} {cite}"
        return Update(Event.TOOL, text, detail)
    return None


def stream(
    caller: Caller,
    *,
    question: str,
    res: Resources,
    budget: Budget | None = None,
    session: str | None = None,
    poll_seconds: float = 0.05,
) -> Iterator[Update]:
    """
    Run one question, yielding progress as it happens.

    The loop runs on a worker thread while this generator watches the trace it
    is building. That is deliberately the *only* coupling: progress is read from
    the same spans the trace records, so what a user sees and what the trace
    shows cannot disagree. Wiring a second set of callbacks through the loop
    would create exactly that opportunity.

    The final `DONE` update carries the `Verdict`, so a caller that wants the
    audited answer -- citations, assumptions, unsourced figures -- gets the same
    object the non-streaming path returns.
    """
    # Supplied up front so this generator can watch the tree fill in. Reading
    # the verdict instead would mean every update arrived after the run
    # finished, which is not streaming.
    live = Trace(session=session)
    outcome: dict[str, Any] = {"trace": live}
    finished = threading.Event()

    def run() -> None:
        try:
            outcome["verdict"] = answer(
                caller,
                question=question,
                res=res,
                budget=budget,
                session=session,
                trace=live,
            )
        except Exception as exc:
            outcome["error"] = exc
        finally:
            finished.set()

    worker = threading.Thread(target=run, daemon=True)
    yield Update(Event.STARTED, "thinking about your question", {"question": question})
    worker.start()

    seen = 0
    while not finished.wait(poll_seconds):
        for update, index in _drain(live, seen):
            seen = index
            yield update

    # Anything recorded between the last poll and the thread finishing.
    for update, index in _drain(live, seen):
        seen = index
        yield update

    if error := outcome.get("error"):
        yield Update(Event.ERROR, f"{type(error).__name__}: {error}")
        return

    verdict = outcome.get("verdict")
    if verdict is None:
        yield Update(Event.ERROR, "the run produced no verdict")
        return

    yield from _closing(verdict)


def _drain(trace: Trace, already: int) -> list[tuple[Update, int]]:
    """
    Progress recorded since the last poll, with the index it was read to.

    Reads the trace rather than a parallel event list, so the stream cannot
    show a step the trace does not contain -- and cannot omit one it does.

    Children are only ever appended, so a plain index is a safe cursor even
    while the worker thread is still writing.
    """
    root = trace.root
    if root is None:
        return []
    out: list[tuple[Update, int]] = []
    for offset, span in enumerate(root.children[already:], start=already + 1):
        if update := _label(span):
            out.append((update, offset))
    return out


def _closing(verdict: Verdict) -> Iterator[Update]:
    if verdict.over_budget:
        yield Update(Event.ERROR, verdict.text, {"over_budget": verdict.over_budget})
    elif verdict.refused:
        yield Update(Event.REFUSED, verdict.text, {"basis": _basis(verdict)})
    elif verdict.clarification:
        yield Update(Event.CLARIFICATION, verdict.clarification)
    else:
        yield Update(Event.ANSWER, verdict.text, {"citations": list(verdict.citations)})

    yield Update(
        Event.DONE,
        "done",
        {
            "verdict": verdict,
            "citations": list(verdict.citations),
            "assumptions": list(verdict.assumptions),
            # Carried so a UI can mark an answer unverified rather than
            # presenting it as checked. Task 5.9 is worth nothing if the
            # streaming path quietly drops it.
            "unsourced_figures": list(verdict.unsourced_figures),
            "trustworthy": verdict.trustworthy,
            "cost": verdict.cost,
        },
    )


def _basis(verdict: Verdict) -> str | None:
    return verdict.routing.refusal_basis if verdict.routing else None
