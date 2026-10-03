"""
Tracing (task 6.10), modelled on Langfuse's guidance but not bound to it.

D4 asks for one trace per user session carrying the user input, the system
prompt, every tool call and result, every intermediate model call and the final
output. That shape is the same whoever stores it, so it is modelled here and
the vendor is a thin adapter (D16).

The structure follows Langfuse's "what does a good trace look like?" guidance,
because it is sound regardless of backend:

* **A trace is one agent run.** One question in, one answer out. Several
  questions in a conversation are separate traces tied together by a session.
* **The root is an `agent`** -- it decides the flow and calls tools with a
  model's guidance -- and its input and output are the *question and the
  answer*, not a JSON blob of arguments. The trace list shows those two fields,
  so they are what a reviewer sees first.
* **Each model invocation is its own generation**, never one generation
  wrapping the loop. Aggregating them hides what the agent decided after each
  tool result, which is the thing you actually want when debugging.
* **A tool call is a sibling of the generation that requested it**, under the
  agent that orchestrates them, rather than dangling at the root.
* **Names are verb-first and low-cardinality** -- `classify-intent`,
  `fetch-provision` -- because names are an API: evaluators, dashboards and
  saved filters target them, and they break silently when a name changes. No
  run-specific values and no model names in them.

**The local exporter is not a placeholder.** A trace written to JSONL survives
any retention window, needs no network and no key, and can be committed as an
artifact (6.10a). The hosted exporter adds a dashboard, not the record.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

JsonDict = dict[str, Any]


class Kind(StrEnum):
    """
    Observation types, named as Langfuse names them.

    `retriever` covers every tool this agent has, which is a consequence of the
    architecture rather than a simplification: ADR-004 makes the database and
    the index read-only build artifacts, so no tool changes state. `tool` is
    kept for the day one does.
    """

    AGENT = "agent"
    GENERATION = "generation"
    RETRIEVER = "retriever"
    TOOL = "tool"
    EVENT = "event"


@dataclass
class Span:
    """
    One recorded step, with its children.

    A tree rather than a list, because nesting is what shows which step an
    action belongs to. A flat sequence leaves tool calls dangling at the root.
    """

    kind: Kind
    name: str
    started_at: float
    ended_at: float | None = None
    input: Any = None
    output: Any = None
    metadata: JsonDict = field(default_factory=dict)
    model: str | None = None
    usage: JsonDict = field(default_factory=dict)
    error: str | None = None
    children: list[Span] = field(default_factory=list)

    @property
    def seconds(self) -> float:
        return (self.ended_at or self.started_at) - self.started_at

    def child(self, kind: Kind, name: str, **kwargs: Any) -> Span:
        span = Span(kind=kind, name=name, started_at=time.time(), **kwargs)
        self.children.append(span)
        return span

    def end(self, **updates: Any) -> Span:
        for key, value in updates.items():
            setattr(self, key, value)
        self.ended_at = time.time()
        return self

    @property
    def descendants(self) -> int:
        return len(self.children) + sum(child.descendants for child in self.children)

    def to_json(self) -> JsonDict:
        out: JsonDict = {
            "kind": self.kind.value,
            "name": self.name,
            "seconds": round(self.seconds, 3),
        }
        for key in ("input", "output", "model", "error"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        if self.metadata:
            out["metadata"] = self.metadata
        if self.usage:
            out["usage"] = self.usage
        if self.children:
            out["children"] = [child.to_json() for child in self.children]
        return out


@dataclass
class Trace:
    """
    One agent run: a question in, an answer out.

    `session` groups several of these, which is what a conversation is. Left
    unset for a one-shot question rather than invented, since a session of one
    tells a reader nothing.
    """

    name: str = "answer-cba-question"
    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    session: str | None = None
    user: str | None = None
    environment: str = "development"
    tags: list[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    root: Span | None = None
    metadata: JsonDict = field(default_factory=dict)
    scores: dict[str, Any] = field(default_factory=dict)
    """
    Judgements made *after* the run -- whether the answer was supported, whether
    any figure was unverified. Tags cannot carry these: tags are immutable and
    set at creation, and these are only known once the answer exists.
    """

    def begin(self, question: str) -> Span:
        self.root = Span(kind=Kind.AGENT, name=self.name, started_at=time.time(), input=question)
        return self.root

    @property
    def events(self) -> int:
        """
        Billable observations: the root plus every descendant.

        The budget reasons about events and the trace about spans; keeping the
        word separate is how an event cap stays in step with what is sent.
        """
        return 0 if self.root is None else 1 + self.root.descendants

    def to_json(self) -> JsonDict:
        return {
            "trace_id": self.trace_id,
            "name": self.name,
            "session": self.session,
            "environment": self.environment,
            "tags": self.tags,
            "started_at": self.started_at,
            "events": self.events,
            "metadata": self.metadata,
            "scores": self.scores,
            "root": self.root.to_json() if self.root else None,
        }


@runtime_checkable
class Exporter(Protocol):
    """
    Where a finished trace goes.

    Must not raise. A tracing backend being down, rate limited or out of quota
    is not a reason for a user's question to fail -- 6.13 settles that tracing
    degrades while spend refuses.
    """

    def export(self, trace: Trace) -> bool: ...


@dataclass
class NullExporter:
    """Drops everything. The default, so tracing is opt-in rather than surprising."""

    dropped: int = 0

    def export(self, trace: Trace) -> bool:
        self.dropped += 1
        return False


@dataclass
class FileExporter:
    """
    Appends each trace as one JSON line.

    The exporter that survives: no network, no key, no retention window, and
    the output can be committed as an artifact (6.10a).
    """

    path: Path
    written: int = 0

    def export(self, trace: Trace) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(trace.to_json(), default=str) + "\n")
        except OSError:
            return False
        self.written += 1
        return True


@dataclass
class CappedExporter:
    """
    Wraps an exporter with the event budget (6.13).

    Applied here rather than inside each vendor adapter, so a free tier's
    allowance is enforced identically however the trace is stored, and
    exceeding it drops the trace instead of failing the request.
    """

    inner: Exporter
    max_events: int
    spent: int = 0
    dropped_traces: int = 0
    dropped_events: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.max_events - self.spent)

    def export(self, trace: Trace) -> bool:
        if self.spent + trace.events > self.max_events:
            self.dropped_traces += 1
            self.dropped_events += trace.events
            return False
        if not self.inner.export(trace):
            return False
        self.spent += trace.events
        return True

    def render(self) -> str:
        line = f"traces: {self.spent}/{self.max_events} events used"
        if self.dropped_traces:
            line += (
                f"; {self.dropped_traces} traces dropped ({self.dropped_events} events) "
                "after the cap -- the questions were still answered"
            )
        return line


def walk(span: Span) -> list[Span]:
    """Depth-first, parents before children."""
    out = [span]
    for child in span.children:
        out.extend(walk(child))
    return out


def summarise(trace: Trace) -> str:
    """A readable digest, for a log line or a test failure."""
    if trace.root is None:
        return f"{trace.trace_id}  empty"
    counts: dict[str, int] = {}
    for span in walk(trace.root):
        counts[span.kind.value] = counts.get(span.kind.value, 0) + 1
    breakdown = ", ".join(f"{name} {n}" for name, n in sorted(counts.items()))
    return f"{trace.trace_id}  {trace.events} events  [{breakdown}]"
