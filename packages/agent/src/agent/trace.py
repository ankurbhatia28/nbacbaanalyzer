"""
Tracing (task 6.10), built without choosing a vendor.

D4 asks for one trace per user session carrying the user input, the system
prompt, every tool call and result, the retrieved context, every intermediate
model call, and the final output. That shape is the same whoever stores it, so
it is modelled here and the vendor is a thin adapter.

That separation is not architectural fussiness. The vendor question is open:
Raindrop's free tier allows 1,000 events a month, which the 6.13a measurement
showed is 60 to 125 questions, and it keeps them for 14 days. Building directly
against one SDK and then moving would mean rewriting the instrumentation rather
than the twenty lines that export it.

**The local exporter is not a placeholder.** A trace written to a JSONL file is
the one that survives a vendor's retention window, works with no network and no
key, and can be committed as an artifact (task 6.10a). The hosted exporter adds
a dashboard, not the record.

**Events are counted the way a vendor bills them**, so the budget's cap (6.13)
binds against the same number the invoice will.
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
    What a span records.

    Each is one billable event on both vendors considered, which is why the
    budget can count spans and trust the number.
    """

    USER_TURN = "user_turn"
    MODEL_CALL = "model_call"
    TOOL_CALL = "tool_call"
    RETRIEVAL = "retrieval"
    ANSWER = "answer"
    REFUSAL = "refusal"


@dataclass
class Span:
    """One recorded step."""

    kind: Kind
    name: str
    started_at: float
    ended_at: float | None = None
    payload: JsonDict = field(default_factory=dict)
    error: str | None = None

    @property
    def seconds(self) -> float:
        return (self.ended_at or self.started_at) - self.started_at

    def to_json(self) -> JsonDict:
        out: JsonDict = {
            "kind": self.kind.value,
            "name": self.name,
            "seconds": round(self.seconds, 3),
            "payload": self.payload,
        }
        if self.error:
            out["error"] = self.error
        return out


@dataclass
class Trace:
    """
    One user session, end to end.

    A session rather than a request, per D4: a conversation is the unit a
    reader wants to follow, and splitting it per turn loses the thing that
    makes a trace useful.
    """

    trace_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    session: str = ""
    started_at: float = field(default_factory=time.time)
    spans: list[Span] = field(default_factory=list)
    metadata: JsonDict = field(default_factory=dict)

    def start(self, kind: Kind, name: str, **payload: Any) -> Span:
        span = Span(kind=kind, name=name, started_at=time.time(), payload=dict(payload))
        self.spans.append(span)
        return span

    def record(self, kind: Kind, name: str, **payload: Any) -> Span:
        """A span with no duration -- something that happened rather than ran."""
        span = self.start(kind, name, **payload)
        span.ended_at = span.started_at
        return span

    @property
    def events(self) -> int:
        """
        Billable events, which is simply the span count.

        Named separately because the budget reasons about events and the trace
        reasons about spans, and conflating the two words is how an event cap
        drifts out of step with what is actually sent.
        """
        return len(self.spans)

    def to_json(self) -> JsonDict:
        return {
            "trace_id": self.trace_id,
            "session": self.session,
            "started_at": self.started_at,
            "events": self.events,
            "metadata": self.metadata,
            "spans": [span.to_json() for span in self.spans],
        }


@runtime_checkable
class Exporter(Protocol):
    """
    Where a finished trace goes.

    Runtime-checkable so a test can assert every exporter satisfies it; the
    vendor adapters are written outside this module and that check is what
    keeps them honest.
    """

    def export(self, trace: Trace) -> bool:
        """
        Send it. Returns whether it was accepted.

        Must not raise. A tracing backend being down, rate limited or out of
        quota is not a reason for a user's question to fail -- 6.13 settles
        that tracing degrades while spend refuses.
        """
        ...


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
    the output can be committed as an artifact (6.10a) so the observability
    story is demonstrable without a live account.
    """

    path: Path
    written: int = 0

    def export(self, trace: Trace) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(trace.to_json(), default=str) + "\n")
        except OSError:
            # A full disk should not fail a question either.
            return False
        self.written += 1
        return True


@dataclass
class CappedExporter:
    """
    Wraps an exporter with the event budget (6.13).

    The cap is applied here rather than inside each vendor adapter, so a free
    tier's allowance is enforced identically however the trace is stored --
    and so exceeding it drops the trace instead of failing the request.
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


def summarise(trace: Trace) -> str:
    """A readable digest, for a log line or a test failure."""
    counts: dict[str, int] = {}
    for span in trace.spans:
        counts[span.kind.value] = counts.get(span.kind.value, 0) + 1
    breakdown = ", ".join(f"{name} {n}" for name, n in sorted(counts.items()))
    return f"{trace.trace_id}  {trace.events} events  [{breakdown}]"
