"""
The HTTP surface (Phase 7; deployed by 8.3).

Three routes, and deliberately nothing that writes:

  GET  /             redirects to /docs, the interactive API page -- there is
                     no page here until the web app exists
  GET  /health       liveness, plus the dataset's build record
  POST /ask          one question, one answer card, as JSON
  POST /ask/stream   the same run as server-sent events: progress while the
                     work happens, then the card

**The two ask routes cannot disagree.** Both end in `card.build` over the
verdict `answer()` returned -- the streaming route reads it from the stream's
final update, which carries the same object (6.9). There is no second
formatting path for a browser to see something the JSON route would not.

**Everything opened is read-only** (ADR-004). The league database and the
retrieval index are build artifacts; this process opens them with `mode=ro`,
and a request has no way to write to either.

**Failure shapes.** A cap refusing a request is a card with status
`unavailable` and the reason, not a 429 with an empty body: the budget returns
a verdict rather than raising, and the reason belongs in front of the user. An
exception inside the run is an `error` event on the stream and a 500 on the
JSON route -- that one is a bug, and should look like one.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from agent import card
from agent.answer import Verdict, answer
from agent.budget import Budget
from agent.llm import Caller
from agent.stream import Event, Update, stream
from agent.tools import Resources
from agent.trace import Exporter, NullExporter
from nbadata.query import Snapshot, snapshot

MAX_QUESTION_CHARS = 500
"""
Longer than any real question, short enough that a pasted document is refused
before it costs anything. The router reads the whole question on every call.
"""


@dataclass
class Service:
    """
    Everything a request needs, built once per process.

    Passed in rather than read from globals so a test can supply a scripted
    caller and fixture data, and exercise the real routes with no key.
    """

    res: Resources
    caller: Caller
    budget: Budget | None = None
    exporter: Exporter = field(default_factory=NullExporter)
    dataset: Snapshot | None = None
    environment: str = "development"

    def __post_init__(self) -> None:
        if self.dataset is None:
            self.dataset = snapshot(self.res.league)

    def finish(self, verdict: Verdict) -> card.AnswerCard:
        """Export the trace and build the card. Export never raises (6.13)."""
        if verdict.trace is not None:
            self.exporter.export(verdict.trace)
        return card.build(verdict, self.dataset)


class Ask(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    session: str | None = Field(default=None, max_length=128)


def _sse(event: str, data: Any) -> str:
    """One server-sent event. JSON on a single line, so no `data:` splitting."""
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _progress(update: Update) -> dict[str, Any]:
    # `detail` on a progress update is small and JSON-safe by construction;
    # the DONE update's detail holds the Verdict and is never sent as-is.
    return {"text": update.text, "detail": update.detail}


def create_app(service: Service, *, allowed_origins: list[str] | None = None) -> FastAPI:
    app = FastAPI(
        title="NBA CBA Analyzer",
        summary="Questions about the 2023 CBA, answered with a citation or refused with a reason.",
    )
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_methods=["GET", "POST"],
            allow_headers=["content-type"],
        )

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/docs")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "schema": card.SCHEMA_VERSION,
            "dataset": service.dataset.to_json() if service.dataset else None,
        }

    @app.post("/ask")
    def ask(body: Ask) -> dict[str, Any]:
        verdict = answer(
            service.caller,
            question=body.question,
            res=service.res,
            budget=service.budget,
            session=body.session,
            environment=service.environment,
        )
        return service.finish(verdict).to_json()

    @app.post("/ask/stream")
    def ask_stream(body: Ask) -> StreamingResponse:
        def events() -> Iterator[str]:
            for update in stream(
                service.caller,
                question=body.question,
                res=service.res,
                budget=service.budget,
                session=body.session,
            ):
                if update.event is Event.DONE:
                    verdict = update.detail["verdict"]
                    yield _sse("card", service.finish(verdict).to_json())
                elif update.event is Event.ERROR and "over_budget" not in update.detail:
                    # A run that raised. Over-budget also arrives as ERROR, but
                    # it is followed by DONE and a card, so it streams as
                    # ordinary progress and the card says why.
                    yield _sse("error", {"text": update.text})
                else:
                    yield _sse(update.event.value, _progress(update))

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            # Proxies buffer by default, which turns a stream into one late
            # response -- the failure 6.9 exists to prevent.
            headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
        )

    return app
