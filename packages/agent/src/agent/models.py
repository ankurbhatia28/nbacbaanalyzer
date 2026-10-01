"""
Which model does which job (D15).

One model for everything is the wrong shape here, because this architecture
deliberately gives the model very little to do. ADR-001 puts the reasoning in
the engine: nothing in `packages/agent` computes a figure or decides a rule.
What is left for a model is classification, selection from closed sets, and
restraint — and those do not all need the same capability.

  ROUTER  sort a question into four classes -- a four-way label.
  INTENT  pick one of the 670 names the document uses -- selection from a
          closed set, not generation.
  ANSWER  orchestrate tools, quote provisions, surface assumptions -- the one
          place judgement and restraint actually matter.

So the small tier handles the first two and the mid tier writes the answer.
**This is a hypothesis, not a finding.** It is recorded as a default and
measured by the 6.1, 6.3 and 6.11 evals, which run per role and per model and
report the table. If the small tier cannot pick the right provision name, the
`INTENT` default moves up and the cost is justified by a number rather than by
a preference.

Cost is not asserted here. Per-token pricing changes and inventing figures in a
docstring would be worse than useless; task 6.12 measures spend per request
from the API's own usage reporting, and 6.13 enforces the cap.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum


class Role(StrEnum):
    """What a model call is for. Each is configured independently."""

    ROUTER = "router"
    INTENT = "intent"
    ANSWER = "answer"


class Tier(StrEnum):
    """
    Relative capability and relative cost, smallest first.

    Named by tier rather than by model id so a default can be reasoned about
    without hard-coding which model is current.
    """

    SMALL = "small"
    MID = "mid"
    LARGE = "large"


MODEL_IDS: dict[Tier, str] = {
    Tier.SMALL: "claude-haiku-4-5-20251001",
    Tier.MID: "claude-sonnet-5",
    Tier.LARGE: "claude-opus-5-5",
}

DEFAULT_TIERS: dict[Role, Tier] = {
    Role.ROUTER: Tier.SMALL,
    Role.INTENT: Tier.SMALL,
    Role.ANSWER: Tier.MID,
}
"""
The starting point, to be moved by measurement.

`ANSWER` is the one role that is not on the small tier, because it is the only
one where the failure mode is a judgement failure rather than a wrong label:
answering a figure out of retrieved prose, or asserting a rule without calling
a tool. Task 6.11 baits exactly that with ~30 adversarial prompts, and the
tier for this role should be whatever passes it.
"""

_ENV_OVERRIDE = {
    Role.ROUTER: "ANTHROPIC_MODEL_ROUTER",
    Role.INTENT: "ANTHROPIC_MODEL_INTENT",
    Role.ANSWER: "ANTHROPIC_MODEL_ANSWER",
}

LEGACY_ENV = "ANTHROPIC_MODEL"
"""
A single-model override, honoured for every role.

Kept because it is what `.env.example` shipped, and because pinning one model
across all roles is exactly what an eval run wants to do.
"""


@dataclass(frozen=True, slots=True)
class Selection:
    """The model chosen for a role, and where that choice came from."""

    role: Role
    model: str
    source: str
    """"default", an environment variable name, or an explicit override."""

    @property
    def tier(self) -> Tier | None:
        for tier, model in MODEL_IDS.items():
            if model == self.model:
                return tier
        return None


def model_for(role: Role, *, override: str | None = None) -> Selection:
    """
    The model to use for a role.

    Precedence: an explicit argument, then the role's own environment variable,
    then the single-model override, then the tier default. Resolution reports
    its source, so a surprising bill can be traced to the thing that set it
    rather than guessed at.
    """
    if override:
        return Selection(role, override, "explicit override")
    specific = os.environ.get(_ENV_OVERRIDE[role])
    if specific:
        return Selection(role, specific, _ENV_OVERRIDE[role])
    shared = os.environ.get(LEGACY_ENV)
    if shared:
        return Selection(role, shared, LEGACY_ENV)
    return Selection(role, MODEL_IDS[DEFAULT_TIERS[role]], "default")


def describe() -> str:
    """The current assignment, for a trace header or a startup log."""
    lines = []
    for role in Role:
        chosen = model_for(role)
        tier = chosen.tier.value if chosen.tier else "unrecognised"
        lines.append(f"  {role.value:<7} {chosen.model:<30} ({tier}, from {chosen.source})")
    return "\n".join(lines)
