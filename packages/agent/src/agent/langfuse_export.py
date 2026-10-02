"""
The Langfuse exporter (D16).

The one vendor-specific file. Task 6.10 modelled the trace shape and kept the
export behind a twenty-line adapter precisely so this file could be written
late, replaced, or deleted without touching the instrumentation.

**Cloud Hobby, not self-hosted.** Self-hosting Langfuse needs Postgres, Redis,
ClickHouse and blob storage behind two containers, which contradicts D11 ("no
managed DB, no persistent disk") and would not fit the free tier this project
deploys to. The one thing self-hosting buys -- retention past 30 days -- is
already covered: `FileExporter` keeps every trace locally for nothing, and
task 6.10a commits five of them to the repo.

**Nothing here may raise.** The `Exporter` contract says so and the reason is
6.13: tracing degrades, spend refuses. A missing SDK, a bad key, a network
failure or an SDK whose shape has moved since this was written all return
`False`, and the question is still answered. That is also why this adapter is
deliberately conservative about the SDK surface it touches.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from .trace import Kind, Trace

GENERATION_KINDS = frozenset({Kind.MODEL_CALL})
"""
Spans Langfuse should treat as generations rather than plain spans.

A generation carries a model and token counts, which is what makes the cost
view in the dashboard work. Everything else -- tool calls, retrieval, the user
turn, the final answer -- is a span.
"""

ENV_KEYS = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
ENV_HOST = "LANGFUSE_BASE_URL"


def configured() -> bool:
    """Whether both keys are present. Checked before importing the SDK."""
    return all(os.environ.get(name) for name in ENV_KEYS)


@dataclass
class LangfuseExporter:
    """
    Sends a trace to Langfuse, or quietly does not.

    The client is built lazily on first export, so importing this module costs
    nothing and needs neither the SDK nor a key -- which is what lets the test
    suite import it unconditionally.
    """

    flush_each: bool = True
    """
    Flush after every trace.

    Right for a request-response service, where the process may not live long
    enough for a background flush. A batch job should set this False and flush
    once at the end.
    """
    exported: int = 0
    failed: int = 0
    last_error: str | None = None
    _client: Any | None = field(default=None, repr=False)
    _unavailable: bool = False

    def _ensure_client(self) -> Any | None:
        if self._client is not None or self._unavailable:
            return self._client
        if not configured():
            self._unavailable = True
            self.last_error = (
                f"{' and '.join(ENV_KEYS)} not set; traces are not being sent. "
                "Langfuse Cloud Hobby keys come from the project settings page."
            )
            return None
        try:
            from langfuse import get_client

            self._client = get_client()
        except Exception as exc:
            self._unavailable = True
            self.last_error = f"{type(exc).__name__}: {exc}"
            return None
        return self._client

    def export(self, trace: Trace) -> bool:
        client = self._ensure_client()
        if client is None:
            self.failed += 1
            return False
        try:
            self._send(client, trace)
        except Exception as exc:
            self.failed += 1
            self.last_error = f"{type(exc).__name__}: {exc}"
            return False
        self.exported += 1
        return True

    def _send(self, client: Any, trace: Trace) -> None:
        """
        One root observation per session, with each recorded span beneath it.

        Our spans are a flat sequence rather than a tree, so each child opens
        and closes inside the root's context and they come out as siblings --
        which is the shape that was recorded, rather than a nesting invented
        here to look tidier.
        """
        with client.start_as_current_observation(
            as_type="span",
            name=trace.session or "session",
            input={"session": trace.session},
            metadata={**trace.metadata, "trace_id": trace.trace_id, "events": trace.events},
        ) as root:
            for span in trace.spans:
                self._send_span(client, span)
            root.update(output={"events": trace.events})
        if self.flush_each:
            client.flush()

    def _send_span(self, client: Any, span: Any) -> None:
        as_type = "generation" if span.kind in GENERATION_KINDS else "span"
        kwargs: dict[str, Any] = {
            "as_type": as_type,
            "name": f"{span.kind.value}:{span.name}",
        }
        if as_type == "generation" and span.payload.get("model"):
            kwargs["model"] = span.payload["model"]
        with client.start_as_current_observation(**kwargs) as observation:
            update: dict[str, Any] = {
                "metadata": {k: v for k, v in span.payload.items() if k != "model"},
            }
            if as_type == "generation":
                # Reported under the names Langfuse costs from. Cache reads are
                # kept separate because at a 97% hit rate (6.8) folding them
                # into input would misstate the bill badly.
                update["usage_details"] = {
                    "input": span.payload.get("input_tokens", 0),
                    "output": span.payload.get("output_tokens", 0),
                    "cache_read_input_tokens": span.payload.get("cached_tokens", 0),
                }
            if span.error:
                update["level"] = "ERROR"
                update["status_message"] = span.error
            observation.update(**update)

    def render(self) -> str:
        line = f"langfuse: {self.exported} traces sent"
        if self.failed:
            line += f", {self.failed} not sent"
        if self.last_error:
            line += f" ({self.last_error})"
        return line
