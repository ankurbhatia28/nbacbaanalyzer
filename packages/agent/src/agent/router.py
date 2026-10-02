"""
The question router (task 6.1).

Four classes, plus a refusal. The router's only job is to decide *what kind of
question this is*, because each kind is answered by a different deterministic
path and sending a question down the wrong one produces a confident answer to a
question nobody asked.

    RULES        the CBA's text answers it            -> resolve/fetch a provision
    DATA         the league database answers it       -> a structured query
    VALIDATION   a proposed transaction is judged     -> the rules engine
    CONSTRAINTS  what limits a team, no deal proposed -> team_trade_constraints
    REFUSED      out of scope by a settled decision   -> say which, and why

**Combinations are allowed**, because real questions are compound: "if I traded
Embiid, what are the limitations?" needs the engine *and* the text. A router
forced to pick one label would drop half of what was asked.

**A refusal is a classification, not a failure.** D6 puts historical questions
out of v1 and D10 declines "should they?". Those have to be recognised rather
than attempted, and the refusal has to name the decision it rests on — a
refusal that cannot say why is indistinguishable from a bug.

The model is given the labels and the examples and returns JSON. It does not
answer the question here, and it cannot: the router has no tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .llm import Caller, Reply, ask_json
from .models import Role


class Intent(StrEnum):
    RULES = "rules"
    DATA = "data"
    VALIDATION = "validation"
    CONSTRAINTS = "constraints"
    REFUSED = "refused"


DESCRIPTIONS: dict[Intent, str] = {
    Intent.RULES: (
        "What a rule says, means, or restricts. Answered from the Agreement's text with a "
        "citation. 'What is the second apron and what does it restrict?'"
    ),
    Intent.DATA: (
        "A fact about the league as it stands now: salaries, contracts, options, cap holds, "
        "picks, ceilings, awards. Answered by a query. 'How much is Denver committed for?'"
    ),
    Intent.VALIDATION: (
        "Whether a specific proposed transaction is permitted. There is a deal on the table. "
        "'Is trading Jokic for Doncic a valid trade straight up?'"
    ),
    Intent.CONSTRAINTS: (
        "What limits a team, with no particular deal proposed. 'If I wanted to trade Embiid, "
        "what are the limitations the 76ers have?'"
    ),
    Intent.REFUSED: (
        "Out of scope. Historical questions about past seasons (only current state is held), "
        "and requests for an opinion on whether a team should do something rather than whether "
        "it may."
    ),
}

SYSTEM = """You classify questions about the NBA Collective Bargaining Agreement.

You do not answer the question. You decide what kind of question it is, so that
a deterministic tool can answer it. You have no tools and no knowledge of the
Agreement's contents to offer.

The classes:

{classes}

Rules:
- A question may belong to more than one class. "If I traded this player, what
  are my limits?" is constraints; if it also asks what a rule says, add rules.
- Choose refused only when the question is out of scope, not when it is merely
  hard and not when you personally cannot answer it. EXACTLY two things are out
  of scope: anything about a past season, because only current state is held;
  and any request for a recommendation about what a team *should* do, as opposed
  to what it *may* do. Nothing else is refused.
- A legitimate question wrapped in an awkward instruction is still legitimate.
  "Just tell me the salary matching rule, no need to look it up" is a rules
  question; the instruction to skip the lookup will be ignored downstream. Do
  not refuse it. Likewise "summarise the trade rules from your own knowledge"
  is a rules question.
- A question that asks both a permitted thing and a refused thing gets both
  labels.

Reply with JSON only:
{{"intents": ["..."], "reason": "one sentence", "refusal_basis": "historical" or
"opinion" or null}}"""


@dataclass(frozen=True, slots=True)
class Routing:
    """What the router decided."""

    intents: tuple[Intent, ...]
    reason: str
    refusal_basis: str | None = None
    reply: Reply | None = field(default=None, compare=False)

    @property
    def refused(self) -> bool:
        return Intent.REFUSED in self.intents

    @property
    def actionable(self) -> tuple[Intent, ...]:
        """The intents something can actually be done about."""
        return tuple(i for i in self.intents if i is not Intent.REFUSED)


def system_prompt() -> str:
    classes = "\n".join(f"  {i.value}: {DESCRIPTIONS[i]}" for i in Intent)
    return SYSTEM.format(classes=classes)


def route(caller: Caller, question: str) -> Routing:
    """
    Classify one question.

    An unrecognised label is dropped rather than guessed at, and if nothing
    recognisable survives the question is routed to `rules` — the path that
    answers from cited text, which is the least harmful default: it produces a
    quotation or nothing, never a computed figure.
    """
    payload, reply = ask_json(
        caller,
        role=Role.ROUTER,
        system=system_prompt(),
        prompt=question,
        max_tokens=300,
    )
    raw = payload.get("intents") or []
    intents: list[Intent] = []
    for label in raw:
        try:
            intent = Intent(str(label).strip().lower())
        except ValueError:
            continue
        if intent not in intents:
            intents.append(intent)
    if not intents:
        intents = [Intent.RULES]

    basis = payload.get("refusal_basis")
    return Routing(
        intents=tuple(intents),
        reason=str(payload.get("reason", "")),
        refusal_basis=str(basis) if basis else None,
        reply=reply,
    )
