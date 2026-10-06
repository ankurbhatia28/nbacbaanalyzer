"""
The free fallback (D23): a `Caller` for OpenRouter, and the switch to it.

Sonnet and Haiku stay the defaults. When Anthropic cannot be used -- the
in-process spend cap is reached, the Console's workspace limit rejects the
call, or the API is rate-limited or overloaded -- `FallbackCaller` sends the
call to a free model on OpenRouter instead of the app refusing. Measured
before choosing (build-plan 8.0a): Nemotron 3 Ultra routed 86.7% against
Haiku's 88.9%, named provisions 84% against 80%, and gave one misleading
answer in 30 adversarial probes, as Sonnet did. It is slower (~50s a
question) and its free endpoint returned 503 on 3-30% of calls, so it is the
fallback and not the default.

**Translation, both ways.** The agent speaks Anthropic's message shape
(content blocks, `tool_use` / `tool_result`); OpenRouter speaks OpenAI's
(`tool_calls`, role `tool`). Each call is translated on the way out and the
reply on the way back, so the answer loop runs unchanged -- including when
the switch happens mid-question, with Anthropic turns already in the history.
Thinking blocks are dropped in translation: they are Anthropic's to verify.

**Free models only.** The OpenRouter key carries the owner's $10 of credit,
which exists to raise the free tier's daily limit, not to be spent. A model
id without the `:free` suffix is refused here rather than billed.

**Reasoning headroom.** Nemotron reasons out of `max_tokens`; at the router's
300 it returned an empty reply every time. A free model's tokens cost
nothing, so each call gets `REASONING_HEADROOM` on top of what was asked.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .llm import Caller, JsonDict, Ledger, Reply, ToolRequest, Usage
from .models import Role

URL = "https://openrouter.ai/api/v1/chat/completions"

DEFAULT_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
"""Every role, unless OPENROUTER_MODEL says otherwise. See the module docstring."""

REASONING_HEADROOM = 4096

ATTEMPTS = 4
"""
Per call, with backoff. The free endpoint's 503s came in short bursts in the
8.0a eval; four attempts over ~15s rode out every one of them, and a question
waiting longer than that is better answered by an error.
"""

_STOP = {"tool_calls": "tool_use", "length": "max_tokens", "stop": "end_turn"}


class FallbackUnavailableError(RuntimeError):
    """OpenRouter did not answer within its attempts."""


def _to_openai(system: str, messages: list[JsonDict]) -> list[JsonDict]:
    out: list[JsonDict] = [{"role": "system", "content": system}]
    for message in messages:
        content = message["content"]
        if isinstance(content, str):
            out.append({"role": message["role"], "content": content})
            continue
        if message["role"] == "assistant":
            text = "".join(b.get("text", "") for b in content if b.get("type") == "text")
            calls = [
                {
                    "id": b["id"],
                    "type": "function",
                    "function": {"name": b["name"], "arguments": json.dumps(b.get("input", {}))},
                }
                for b in content
                if b.get("type") == "tool_use"
            ]
            turn: JsonDict = {"role": "assistant", "content": text or None}
            if calls:
                turn["tool_calls"] = calls
            out.append(turn)
            continue
        # A user turn: tool results become `tool` messages, text stays user.
        texts: list[str] = []
        for block in content:
            if block.get("type") == "tool_result":
                body = block.get("content")
                if isinstance(body, list):
                    body = "".join(part.get("text", "") for part in body)
                out.append({"role": "tool", "tool_call_id": block["tool_use_id"], "content": body})
            elif block.get("type") == "text":
                texts.append(block["text"])
        if texts:
            out.append({"role": "user", "content": "\n".join(texts)})
    return out


def _to_openai_tools(tools: list[JsonDict]) -> list[JsonDict]:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]


def _from_openai(data: JsonDict, model: str) -> tuple[str, tuple[ToolRequest, ...], list[JsonDict]]:
    """The reply's text, its tool requests, and the turn as Anthropic blocks."""
    message = data["choices"][0]["message"]
    text = message.get("content") or ""
    raw: list[JsonDict] = [{"type": "text", "text": text}] if text else []
    requests: list[ToolRequest] = []
    for call in message.get("tool_calls") or []:
        try:
            arguments = json.loads(call["function"].get("arguments") or "{}")
        except json.JSONDecodeError:
            arguments = {}
        if not isinstance(arguments, dict):
            # Handed to the tool as-is it would fail there; empty arguments
            # come back from tools.call as an error the model can correct.
            arguments = {}
        request = ToolRequest(id=call["id"], name=call["function"]["name"], arguments=arguments)
        requests.append(request)
        raw.append({"type": "tool_use", "id": request.id, "name": request.name, "input": arguments})
    return text, tuple(requests), raw


class OpenRouterCaller:
    """The `Caller` for OpenRouter's free models."""

    def __init__(
        self,
        ledger: Ledger | None = None,
        api_key: str | None = None,
        *,
        model: str | None = None,
        attempts: int = ATTEMPTS,
        sleep: Callable[[float], None] = time.sleep,
        post: Callable[..., Any] | None = None,
    ) -> None:
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY is not set; the fallback needs it")
        self.model = model or os.environ.get("OPENROUTER_MODEL") or DEFAULT_MODEL
        if not self.model.endswith(":free"):
            raise ValueError(
                f"{self.model} is not a free model; the fallback only uses ':free' ids, "
                "so the key's credit is never spent"
            )
        self._key = key
        self.ledger = ledger if ledger is not None else Ledger()
        self.attempts = attempts
        self._sleep = sleep
        if post is None:
            import httpx2

            post = httpx2.Client(timeout=180.0).post
        self._post = post

    def __call__(
        self,
        *,
        role: Role,
        system: str,
        messages: list[JsonDict],
        max_tokens: int = 1024,
        tools: list[JsonDict] | None = None,
    ) -> Reply:
        body: JsonDict = {
            "model": self.model,
            "max_tokens": max_tokens + REASONING_HEADROOM,
            "messages": _to_openai(system, messages),
        }
        if tools:
            body["tools"] = _to_openai_tools(tools)
        data = self._send(body)
        text, requests, raw = _from_openai(data, self.model)
        reported = data.get("usage") or {}
        usage = Usage(
            input_tokens=reported.get("prompt_tokens", 0) or 0,
            output_tokens=reported.get("completion_tokens", 0) or 0,
        )
        self.ledger.record(role, usage)
        reason = data["choices"][0].get("finish_reason")
        return Reply(
            text=text,
            usage=usage,
            model=self.model,
            stop_reason=_STOP.get(reason, reason),
            tool_requests=requests,
            raw_content=tuple(raw),
        )

    def _send(self, body: JsonDict) -> JsonDict:
        failures: list[str] = []
        for attempt in range(self.attempts):
            if attempt:
                self._sleep(min(2**attempt, 8))
            try:
                response = self._post(
                    URL, json=body, headers={"Authorization": f"Bearer {self._key}"}
                )
                payload = response.json()
            except Exception as exc:  # network, timeout, a body that is not JSON
                failures.append(type(exc).__name__)
                continue
            error = payload.get("error") if isinstance(payload, dict) else None
            if response.status_code == 200 and not error and payload.get("choices"):
                return dict(payload)
            failures.append(str(error.get("code") if error else response.status_code))
        raise FallbackUnavailableError(
            f"OpenRouter {self.model}: no answer after {self.attempts} attempts "
            f"({', '.join(failures)})"
        )


# -- the switch ------------------------------------------------------------

BILLING_COOLDOWN = 3600.0
"""A spend limit does not lift in a minute; retry Anthropic hourly."""

CAPACITY_COOLDOWN = 60.0
"""Rate limits and overload do; retry Anthropic after a minute."""


def anthropic_unavailable(exc: Exception) -> tuple[str, float] | None:
    """
    Why Anthropic cannot take calls right now, and for how long to stop asking.

    None for anything else -- a malformed request or a bug is not a reason to
    switch models, and switching would hide it.
    """
    try:
        import anthropic
    except ImportError:  # pragma: no cover - the SDK is a dependency
        return None
    message = str(exc).lower()
    if isinstance(exc, anthropic.BadRequestError | anthropic.PermissionDeniedError) and (
        "usage limit" in message or "credit balance" in message or "spend limit" in message
    ):
        return "the Anthropic spend limit has been reached", BILLING_COOLDOWN
    if isinstance(exc, anthropic.RateLimitError):
        return "Anthropic is rate-limiting this key", CAPACITY_COOLDOWN
    if isinstance(exc, anthropic.InternalServerError) or (
        isinstance(exc, anthropic.APIStatusError) and exc.status_code >= 500
    ):
        return "Anthropic is overloaded or unavailable", CAPACITY_COOLDOWN
    return None


@dataclass
class FallbackCaller:
    """
    Anthropic first; OpenRouter while Anthropic cannot be used.

    Sticky for a cooldown, so a question that hit the limit does not try
    Anthropic again on every round, and neither does the next question.
    """

    primary: Caller
    fallback: Caller
    classify: Callable[[Exception], tuple[str, float] | None] = anthropic_unavailable
    clock: Callable[[], float] = time.monotonic
    reason: str | None = None
    _until: float = field(default=0.0, repr=False)

    def engage(self, reason: str, seconds: float) -> None:
        self.reason = reason
        self._until = self.clock() + seconds

    @property
    def engaged(self) -> bool:
        return self.reason is not None and self.clock() < self._until

    def __call__(
        self,
        *,
        role: Role,
        system: str,
        messages: list[JsonDict],
        max_tokens: int = 1024,
        tools: list[JsonDict] | None = None,
    ) -> Reply:
        kwargs: dict[str, Any] = dict(
            role=role, system=system, messages=messages, max_tokens=max_tokens, tools=tools
        )
        if not self.engaged:
            try:
                return self.primary(**kwargs)
            except Exception as exc:
                why = self.classify(exc)
                if why is None:
                    raise
                self.engage(*why)
        return self.fallback(**kwargs)
