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
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from .trace import Kind, Trace

ENV_KEYS = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
ENV_HOST = "LANGFUSE_BASE_URL"


def configured() -> bool:
    """Whether both keys are present. Checked before importing the SDK."""
    return all(os.environ.get(name) for name in ENV_KEYS)


@contextmanager
def _no_attributes(**_: Any) -> Iterator[None]:
    """Stand-in for `propagate_attributes` when the SDK is not installed."""
    yield


def propagate(**attributes: Any) -> Any:
    """
    `langfuse.propagate_attributes`, resolved at call time.

    Looked up here rather than imported at module scope for the same reason the
    client is built lazily: the SDK is an optional dependency, and the suite has
    to pass without it. A test driving this with a fake client never reaches a
    real SDK call, and should not need one installed to get that far.
    """
    try:
        from langfuse import propagate_attributes
    except ImportError:
        return _no_attributes(**attributes)
    return propagate_attributes(**attributes)


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
        Replay the recorded tree onto Langfuse's, depth first.

        Written against the **v4** SDK, verified against the installed version
        rather than recalled. v3's `update_current_trace` does not exist in v4;
        trace-level attributes are set with the module-level
        `propagate_attributes`, and `set_trace_io` is deprecated in favour of
        the root observation's own input and output.

        `propagate_attributes` wraps the root's creation because it only
        applies to the active span and to spans created after it -- called
        late, the earlier observations drop out of any aggregation by session
        or environment.
        """
        if trace.root is None:
            return
        # Only short, stable dimensions are propagated. A propagated attribute
        # value is capped at 200 characters and dropped with a warning above
        # it -- the citation list blew through that on the first live run. The
        # per-run detail goes on the root observation's metadata instead, where
        # it belongs anyway: it describes this run, not every span in it.
        with (
            propagate(
                session_id=trace.session,
                user_id=trace.user,
                tags=trace.tags or None,
                environment=trace.environment,
                trace_name=trace.name,
            ),
            client.start_as_current_observation(
                as_type=trace.root.kind.value,
                name=trace.root.name,
                input=trace.root.input,
                metadata=trace.metadata or None,
            ) as root,
        ):
            for child in trace.root.children:
                self._send_span(client, root, child)
            root.update(output=trace.root.output)
            self._send_scores(client, trace)

        if self.flush_each:
            client.flush()

    def _send_span(self, client: Any, parent: Any, span: Any) -> None:
        """
        One observation, with its children beneath it.

        Nesting comes from the context manager: an observation created inside
        another becomes its child. That reproduces the recorded tree, so a tool
        call stays a sibling of the generation that requested it rather than
        being flattened to the root.

        An `event` is not a valid `as_type` -- the SDK warns and silently
        downgrades it to a span. Events are created on their parent instead,
        which is also the better fit: they are instants with no duration and
        no children.
        """
        if span.kind is Kind.EVENT:
            parent.create_event(
                name=span.name,
                input=span.input,
                output=span.output,
                metadata=span.metadata or None,
            )
            return

        kwargs: dict[str, Any] = {"as_type": span.kind.value, "name": span.name}
        if span.input is not None:
            kwargs["input"] = span.input
        if span.model:
            kwargs["model"] = span.model
        with client.start_as_current_observation(**kwargs) as observation:
            update: dict[str, Any] = {}
            if span.output is not None:
                update["output"] = span.output
            if span.metadata:
                update["metadata"] = span.metadata
            if span.usage:
                update["usage_details"] = span.usage
            if span.error:
                update["level"] = "ERROR"
                update["status_message"] = span.error
            if update:
                observation.update(**update)
            for child in span.children:
                self._send_span(client, observation, child)

    def _send_scores(self, client: Any, trace: Trace) -> None:
        """
        Judgements made after the run.

        Tags cannot carry these: tags are immutable and set at creation, while
        whether an answer was supported, or carried an unverified figure, is
        only known once it exists. A failing score does not fail the export --
        it is the least important thing in the trace.
        """
        for name, value in trace.scores.items():
            try:
                client.score_current_trace(name=name, value=value)
            except Exception as exc:
                self.last_error = f"score {name}: {type(exc).__name__}: {exc}"

    def render(self) -> str:
        line = f"langfuse: {self.exported} traces sent"
        if self.failed:
            line += f", {self.failed} not sent"
        if self.last_error:
            line += f" ({self.last_error})"
        return line
