"""
Question to structured intent (task 6.3), and the test of D14 option A.

The router decides what *kind* of question this is. This step decides what the
question is *about*: which provisions to read, and which players and teams it
names. Everything it produces is then resolved deterministically — a provision
name against the document's own vocabulary, a player name against the database
— so the model's output is a *selection*, never an assertion.

**The vocabulary goes in the prompt.** All 612 names the document gives its own
provisions, which is about 3,000 tokens and therefore cacheable (task 6.8), so
it costs almost nothing after the first call. Handing the model the closed set
is what makes this safe: a name it invents resolves to nothing rather than to
something plausible, and D14 measured that naming reaches the right provision
where searching for a paraphrase reaches it 20% of the time.

**Ambiguity asks, it does not guess.** Two players called Williams is not a
coin flip. An ambiguous entity produces a clarification and no plan, because
answering about the wrong player is worse than one more turn.

What this step cannot do is invent capability: a name outside the vocabulary,
or a player not under contract, comes back unresolved and is reported as such.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from nbadata.query import lookup_player
from rag import index as ix

from .llm import Caller, Reply, ask_json
from .models import Role
from .router import Intent as Kind

SYSTEM = """You turn a question about the NBA Collective Bargaining Agreement into a
plan for deterministic tools to execute. You do not answer the question and you
have no tools here.

Two jobs.

1. Name the provisions the question is about, choosing ONLY from the list below.
   These are the names the Agreement itself gives its rules. Copy a name exactly
   as it appears.

   Many specific rules have no name of their own -- the Agreement did not give
   every subsection a heading. When the precise rule is not in the list, name
   the BROADER provision that contains it. "Trade Rules" is the right answer for
   a question about a particular trade restriction that is not itself listed.
   Naming the containing provision reaches the right part of the document;
   naming nothing reaches none of it, so prefer the broader name over an empty
   list.

   Name up to THREE provisions, most likely first. The rules overlap -- a
   question about matching salary in a trade touches the exception that permits
   it and the restrictions that limit it -- and fetching two or three short
   provisions costs far less than missing the one that answers the question.
   Name fewer only when you are confident.

   Return an empty list only when the question is not about the Agreement's text
   at all. Never invent a name: one that is not in the list reaches nothing.

2. List the people and teams the question names, verbatim as the user wrote them.
   Do not correct spellings or expand nicknames; resolution happens elsewhere.

The provision names available to you:

{vocabulary}

Reply with JSON only:
{{"provisions": ["most likely name", "next", "next"], "players": ["name as written", ...],
  "teams": ["name as written", ...], "reason": "one sentence"}}"""


@dataclass(frozen=True, slots=True)
class Entity:
    """A resolved person, or the candidates when resolution was ambiguous."""

    asked_as: str
    key: str | None = None
    display_name: str | None = None
    candidates: tuple[str, ...] = ()

    @property
    def resolved(self) -> bool:
        return self.key is not None

    @property
    def ambiguous(self) -> bool:
        return self.key is None and len(self.candidates) > 1


@dataclass(frozen=True, slots=True)
class Plan:
    """What the tools should do, with everything already resolved."""

    question: str
    kinds: tuple[Kind, ...]
    citations: tuple[str, ...] = ()
    """Provisions to fetch, resolved from names the model chose."""
    named_as: tuple[str, ...] = ()
    """The names the model used, in the same order, so a trace can show them."""
    unresolved_names: tuple[str, ...] = ()
    """Names the model produced that the document does not use."""
    players: tuple[Entity, ...] = ()
    teams: tuple[str, ...] = ()
    reason: str = ""
    reply: Reply | None = field(default=None, compare=False)

    @property
    def clarification(self) -> str | None:
        """
        What to ask the user, if anything, before doing the work.

        Only ambiguity produces this. An unresolved provision name is not a
        question for the user -- they did not choose it, the model did.
        """
        unclear = [entity for entity in self.players if entity.ambiguous]
        if not unclear:
            return None
        parts = []
        for entity in unclear:
            options = ", ".join(entity.candidates[:6])
            parts.append(f"{entity.asked_as!r} could be: {options}")
        return "Which did you mean? " + "; ".join(parts)

    @property
    def actionable(self) -> bool:
        return self.clarification is None


def system_prompt(conn: sqlite3.Connection) -> str:
    """
    The prompt, with the vocabulary inlined.

    Built from the index rather than a constant so it cannot drift from the
    names that actually resolve.
    """
    return SYSTEM.format(vocabulary="\n".join(ix.vocabulary_names(conn)))


def _resolve_players(conn: sqlite3.Connection, names: list[str]) -> tuple[Entity, ...]:
    out: list[Entity] = []
    for name in names:
        matches = lookup_player(conn, name)
        if len(matches) == 1:
            out.append(
                Entity(
                    asked_as=name, key=matches[0].player_key, display_name=matches[0].display_name
                )
            )
        else:
            out.append(
                Entity(
                    asked_as=name,
                    candidates=tuple(m.display_name for m in matches[:8]),
                )
            )
    return tuple(out)


def plan(
    caller: Caller,
    *,
    question: str,
    kinds: tuple[Kind, ...],
    cba: sqlite3.Connection,
    league: sqlite3.Connection,
) -> Plan:
    """
    Build a plan for one question.

    Provision names are resolved exactly. A name the document does not use is
    collected on `unresolved_names` rather than approximated: D14 settled that
    fuzzy matching here would cite the wrong provision silently, which is the
    failure this project is arranged against.
    """
    payload, reply = ask_json(
        caller,
        role=Role.INTENT,
        system=system_prompt(cba),
        prompt=question,
        max_tokens=500,
    )

    citations: list[str] = []
    named_as: list[str] = []
    unresolved: list[str] = []
    for raw in payload.get("provisions") or []:
        name = str(raw).strip()
        if not name:
            continue
        resolved = ix.resolve_term(cba, name)
        if resolved is None:
            unresolved.append(name)
            continue
        citation = resolved[0]
        if citation not in citations:
            citations.append(citation)
            named_as.append(name)

    players = _resolve_players(league, [str(p) for p in (payload.get("players") or [])])
    teams = tuple(str(t) for t in (payload.get("teams") or []))

    return Plan(
        question=question,
        kinds=kinds,
        citations=tuple(citations),
        named_as=tuple(named_as),
        unresolved_names=tuple(unresolved),
        players=players,
        teams=teams,
        reason=str(payload.get("reason", "")),
        reply=reply,
    )
