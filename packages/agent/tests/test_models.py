"""
Per-role effort, and what the Anthropic caller actually sends (task 8.0).

No API key is needed: the client is replaced by a fake that records the
request, because the contract here is the request's shape, not any reply.
"""

from __future__ import annotations

from typing import Any

import anthropic
import pytest

from agent.llm import AnthropicCaller
from agent.models import DEFAULT_EFFORT, Role, effort_for


class _Messages:
    def __init__(self) -> None:
        self.sent: dict[str, Any] = {}

    def create(self, **kwargs: Any) -> anthropic.types.Message:
        self.sent = kwargs
        return anthropic.types.Message(
            id="msg_test",
            type="message",
            role="assistant",
            model=kwargs["model"],
            content=[anthropic.types.TextBlock(type="text", text="ok")],
            stop_reason="end_turn",
            usage=anthropic.types.Usage(input_tokens=1, output_tokens=1),
        )


class _Client:
    def __init__(self) -> None:
        self.messages = _Messages()


def _send(role: Role, *, cache: bool = True) -> dict[str, Any]:
    caller = AnthropicCaller(api_key="test", cache=cache)
    client = _Client()
    caller._client = client  # type: ignore[assignment]
    caller(role=role, system="s", messages=[{"role": "user", "content": "q"}])
    return client.messages.sent


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for role in Role:
        monkeypatch.delenv(f"ANTHROPIC_EFFORT_{role.name}", raising=False)


def test_the_environment_overrides_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_EFFORT_ANSWER", "low")
    assert effort_for(Role.ANSWER) == "low"


def test_the_small_tier_roles_send_no_effort() -> None:
    # Haiku 4.5 rejects the parameter, so the router must never send it.
    assert Role.ROUTER not in DEFAULT_EFFORT
    assert "output_config" not in _send(Role.ROUTER)


def test_the_answer_role_sends_its_effort() -> None:
    assert _send(Role.ANSWER)["output_config"] == {"effort": DEFAULT_EFFORT[Role.ANSWER]}


def test_the_conversation_is_cached_as_well_as_the_system_prompt() -> None:
    sent = _send(Role.ANSWER)
    assert sent["cache_control"] == {"type": "ephemeral"}
    assert sent["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_caching_off_sends_no_breakpoint() -> None:
    sent = _send(Role.ANSWER, cache=False)
    assert "cache_control" not in sent
    assert "cache_control" not in sent["system"][0]
