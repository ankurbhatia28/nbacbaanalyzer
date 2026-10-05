"""
The model client, and the accounting around it (tasks 6.4, 6.12).

Three things live here that are easy to get wrong if they are spread out.

**A seam for testing.** `Caller` is a protocol, so every test in this package
runs against a stub and the suite never spends money or needs a key. A test
that only passes with an API key is a test that stops running.

**Usage accounting.** Every call records its tokens, so cost per request is
measured from the API's own reporting rather than estimated. 6.13's spend cap
needs a real number to enforce, and an estimate would be the wrong thing to
enforce against.

**Structured output with a bounded retry.** The model is asked for JSON and
given one chance to fix a malformed reply, with the parse error handed back to
it. Unbounded retries on a confused model burn budget; zero retries throw away
a turn that a single error message would have salvaged.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

from .models import Role, effort_for, model_for

JsonDict = dict[str, Any]

MAX_JSON_ATTEMPTS = 2
"""The first try plus one correction. See the module docstring."""

CACHE_BREAKPOINT = {"type": "ephemeral"}
"""
Marks the end of the stable prefix for prompt caching (task 6.8).

Placed on the **system block**, not on the last tool. The request is assembled
tools-then-system, so a breakpoint after the system text covers both; marking
the last tool caches the tools and leaves the system prompt out. Measured on a
2,700-token prefix: the system block caches 2,650 tokens against 2,565 for the
last tool, so the placement is worth getting right.

Applied unconditionally. A prefix below the model's minimum is silently
*ignored* rather than charged, so there is no threshold constant here to go
stale; what caching is worth is reported by the ledger instead of assumed.

The minimums, measured by bisection rather than recalled:

    Sonnet 5     1,024 tokens   (a 2,650-token prefix caches)
    Haiku 4.5    4,096 tokens   (3,470 does not cache, 4,617 does)

That asymmetry decides where caching pays. The answer role runs on Sonnet with
a 2,700-token tool prefix and saves 97%. The router's 447 tokens and the intent
step's ~3,150 both sit under Haiku's 4,096, so neither caches -- the intent
prompt by a frustratingly small margin.
"""


@dataclass(frozen=True, slots=True)
class Usage:
    """Tokens for one call, as the API reported them."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
        )


@dataclass(frozen=True, slots=True)
class ToolRequest:
    """A tool the model asked to run, with the id its result must carry back."""

    id: str
    name: str
    arguments: JsonDict


@dataclass(frozen=True, slots=True)
class Reply:
    """What a call returned: the text, the tokens, and which model answered."""

    text: str
    usage: Usage
    model: str
    stop_reason: str | None = None
    tool_requests: tuple[ToolRequest, ...] = ()
    raw_content: tuple[JsonDict, ...] = ()
    """
    The assistant turn verbatim, to be replayed when returning tool results.

    Kept because a tool-use turn has to go back into the conversation exactly
    as it came out; reconstructing it from `text` would drop the tool_use
    blocks and the model would have nothing to attach results to.
    """

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_requests)


class Caller(Protocol):
    """
    The one thing the agent needs from a model.

    Deliberately narrow. Tool-use orchestration is built on top of this rather
    than inside it, so the loop can be tested step by step.
    """

    def __call__(
        self,
        *,
        role: Role,
        system: str,
        messages: list[JsonDict],
        max_tokens: int = 1024,
        tools: list[JsonDict] | None = None,
    ) -> Reply: ...


@dataclass
class Ledger:
    """
    Running usage, per role and in total.

    Per role because the point of D15 is that roles cost differently, and a
    single total cannot tell you whether the answer model or the router is
    responsible for a bill.
    """

    by_role: dict[Role, Usage] = field(default_factory=dict)
    calls: int = 0

    def record(self, role: Role, usage: Usage) -> None:
        self.by_role[role] = self.by_role.get(role, Usage()) + usage
        self.calls += 1

    @property
    def total(self) -> Usage:
        out = Usage()
        for usage in self.by_role.values():
            out = out + usage
        return out

    def cache_hit_rate(self, role: Role | None = None) -> float:
        """
        The share of prefix tokens served from cache rather than recomputed.

        Denominator is cache reads plus cache writes, not total input: the
        per-turn message is never cacheable, so including it would understate
        how well the *prefix* is being reused.
        """
        usage = self.by_role.get(role, Usage()) if role else self.total
        cacheable = usage.cache_read_tokens + usage.cache_write_tokens
        return usage.cache_read_tokens / cacheable if cacheable else 0.0

    def render(self) -> str:
        lines = [f"{self.calls} model calls"]
        for role, usage in sorted(self.by_role.items()):
            lines.append(
                f"  {role.value:<7} in {usage.input_tokens:>7,}  out {usage.output_tokens:>6,}"
                f"  cache r/w {usage.cache_read_tokens:>7,}/{usage.cache_write_tokens:<7,}"
                f"  hit {self.cache_hit_rate(role):>5.0%}"
            )
        total = self.total
        lines.append(
            f"  {'total':<7} in {total.input_tokens:>7,}  out {total.output_tokens:>6,}"
            f"  cache r/w {total.cache_read_tokens:>7,}/{total.cache_write_tokens:<7,}"
            f"  hit {self.cache_hit_rate():>5.0%}"
        )
        if total.cache_read_tokens == 0 and total.cache_write_tokens == 0:
            lines.append(
                "  (nothing cached: a prefix below the model's minimum is ignored, not charged)"
            )
        return "\n".join(lines)


class AnthropicCaller:
    """
    The real client. Constructed only where a key is present.

    Imported lazily inside `__init__` so that merely importing this module --
    which every test in the package does -- does not require the SDK to be
    installed or a key to be set.
    """

    def __init__(
        self,
        ledger: Ledger | None = None,
        api_key: str | None = None,
        *,
        cache: bool = True,
    ) -> None:
        import anthropic

        self.cache = cache
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set; the agent layer needs it, the engine does not"
            )
        self._client = anthropic.Anthropic(api_key=key)
        self.ledger = ledger if ledger is not None else Ledger()

    def __call__(
        self,
        *,
        role: Role,
        system: str,
        messages: list[JsonDict],
        max_tokens: int = 1024,
        tools: list[JsonDict] | None = None,
    ) -> Reply:
        import anthropic

        selection = model_for(role)
        system_blocks: list[JsonDict] = [{"type": "text", "text": system}]
        if self.cache:
            system_blocks[0]["cache_control"] = dict(CACHE_BREAKPOINT)
        kwargs: JsonDict = {
            "model": selection.model,
            "max_tokens": max_tokens,
            "system": system_blocks,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        if self.cache:
            # A second, moving breakpoint at the end of the conversation. The
            # system breakpoint alone leaves every tool round re-sending the
            # whole history at the full input price: a trade question that ran
            # six rounds billed 115,285 uncached input tokens against 24,891
            # cached (task 8.0).
            kwargs["cache_control"] = dict(CACHE_BREAKPOINT)
        effort = effort_for(role)
        if effort:
            kwargs["output_config"] = {"effort": effort}
        response = self._client.messages.create(**kwargs)

        usage = Usage(
            input_tokens=getattr(response.usage, "input_tokens", 0) or 0,
            output_tokens=getattr(response.usage, "output_tokens", 0) or 0,
            cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
        )
        self.ledger.record(role, usage)
        # Narrowed by isinstance rather than by a `type == "text"` check: the
        # response union has a dozen block kinds and only TextBlock carries
        # `.text`, so the check has to be one the type checker can follow.
        text = "".join(
            block.text for block in response.content if isinstance(block, anthropic.types.TextBlock)
        )
        requests = tuple(
            ToolRequest(
                id=block.id,
                name=block.name,
                arguments=dict(block.input) if isinstance(block.input, dict) else {},
            )
            for block in response.content
            if isinstance(block, anthropic.types.ToolUseBlock)
        )
        return Reply(
            text=text,
            usage=usage,
            model=selection.model,
            stop_reason=getattr(response, "stop_reason", None),
            tool_requests=requests,
            raw_content=tuple(block.model_dump(exclude_none=True) for block in response.content),
        )


class JsonReplyError(ValueError):
    """The model did not return usable JSON within its attempts."""


def _extract_json(text: str) -> JsonDict:
    """
    Parse a JSON object out of a reply.

    Tolerates a fenced block and surrounding prose, because models produce
    both, but does not tolerate ambiguity: if no object can be found the caller
    retries with the error rather than this function guessing.
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("```")[1] if "```" in stripped[3:] else stripped[3:]
        stripped = stripped.removeprefix("json").strip()
    start, end = stripped.find("{"), stripped.rfind("}")
    if start < 0 or end <= start:
        raise JsonReplyError(f"no JSON object in reply: {text[:200]!r}")
    parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise JsonReplyError("reply was JSON but not an object")
    return parsed


def ask_json(
    caller: Caller,
    *,
    role: Role,
    system: str,
    prompt: str,
    max_tokens: int = 512,
) -> tuple[JsonDict, Reply]:
    """
    Ask for a JSON object, with one correction attempt.

    The retry hands the model its own parse error. A bare "try again" wastes
    the turn; naming what was wrong is usually enough.
    """
    messages: list[JsonDict] = [{"role": "user", "content": prompt}]
    last: Exception | None = None
    reply: Reply | None = None
    for attempt in range(MAX_JSON_ATTEMPTS):
        reply = caller(role=role, system=system, messages=messages, max_tokens=max_tokens)
        try:
            return _extract_json(reply.text), reply
        except (JsonReplyError, json.JSONDecodeError) as exc:
            last = exc
            if attempt == MAX_JSON_ATTEMPTS - 1:
                break
            messages = [
                *messages,
                {"role": "assistant", "content": reply.text},
                {
                    "role": "user",
                    "content": (
                        f"That did not parse as JSON ({exc}). Reply with the JSON object only."
                    ),
                },
            ]
    raise JsonReplyError(f"no usable JSON after {MAX_JSON_ATTEMPTS} attempts: {last}")
