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
    Role.INTENT: Tier.MID,
    Role.ANSWER: Tier.MID,
}
"""
Measured, and already moved once.

`ROUTER` stays small: 88.9% exact-set accuracy against the mid tier's 91.1%,
both at 100% refusal recall, which is not worth a tier for a four-way label.

`INTENT` **moved up** after 6.3 measured it. Naming the right provision is the
whole of D14 option A, and the small tier reached 64% of the 100% ceiling
against the mid tier's 80%. Two things decided it, and the second was a
surprise:

  * 16 points of accuracy on the task the retrieval strategy depends on.
  * The prompt carries the document's 612-name vocabulary, about 3,150 tokens.
    That is **above the mid tier's 1,024-token cache minimum and below the
    small tier's 4,096**, so it caches on the larger model and not the smaller
    one. Uncached input across 25 calls: 609 tokens on the mid tier against
    83,399 on the small one. The cheaper model is the one that resends the
    prompt every time.

`ANSWER` is mid tier because it is the only role whose failure is a judgement
failure rather than a wrong label: answering a figure out of retrieved prose,
or asserting a rule without calling a tool. Task 6.11 baits exactly that, and
the tier for this role should be whatever passes it.
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


_EFFORT_ENV = {
    Role.ROUTER: "ANTHROPIC_EFFORT_ROUTER",
    Role.INTENT: "ANTHROPIC_EFFORT_INTENT",
    Role.ANSWER: "ANTHROPIC_EFFORT_ANSWER",
}

DEFAULT_EFFORT: dict[Role, str] = {Role.ANSWER: "medium"}
"""
Thinking depth per role, sent as `output_config.effort`; a role absent here
sends nothing and gets the model's own default.

Only for models that take the parameter -- Haiku 4.5 rejects it, which is why
the router has no default.

`ANSWER` is `medium`, one below Sonnet 5's default of `high`, measured in task
8.0 on the trade question that had been coming back empty: three runs each at
the same 8,000-token ceiling, `high` averaged $0.31 and 86s, `medium` $0.245
and 58s, and every run of both answered. `medium` also gave the same verdict
three times out of three.
"""


def effort_for(role: Role) -> str | None:
    """The effort level for a role: its environment variable, then the default."""
    return os.environ.get(_EFFORT_ENV[role]) or DEFAULT_EFFORT.get(role)
