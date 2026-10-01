"""
Intent evals (task 6.3) -- whether a model can actually name the provision.

D14 settled that *naming* a provision reaches its text where searching for a
paraphrase mostly does not, and measured the ceiling: all 25 provisions the
engine cites are reachable by name, 100%. What that measurement could not tell
us is whether a model picks the right name, because that needs a model.

This is that number. The same 25 questions, phrased as a user would ask them,
scored on whether the plan's resolved citation reaches the provision the
question is about.

Three outcomes are tracked separately because they fail differently:

  reached      the plan's citation leads to the expected text -- the win
  wrong        a real name, but not the right provision -- a selection error
  unresolved   a name the document does not use -- the model invented one

The third is the one that matters for safety. An invented name resolves to
nothing, so it degrades into "I could not find that" rather than a confident
citation of the wrong rule. A selection error is worse: it reads correctly.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from rag import index as ix
from rag.evals import RULES, Question
from rag.retrieve import for_citation

from .intent import plan
from .llm import Caller, JsonReplyError
from .router import Intent as Kind


@dataclass(frozen=True, slots=True)
class Outcome:
    question: Question
    named: tuple[str, ...]
    citations: tuple[str, ...]
    unresolved: tuple[str, ...]
    reached: bool
    error: str | None = None

    @property
    def invented(self) -> bool:
        return bool(self.unresolved) and not self.reached

    @property
    def mis_selected(self) -> bool:
        """A real name, but the wrong provision. The dangerous failure."""
        return bool(self.citations) and not self.reached


@dataclass
class Report:
    outcomes: list[Outcome] = field(default_factory=list)

    @property
    def scored(self) -> int:
        return len(self.outcomes)

    @property
    def reached(self) -> int:
        return sum(1 for o in self.outcomes if o.reached)

    @property
    def mis_selected(self) -> int:
        return sum(1 for o in self.outcomes if o.mis_selected)

    @property
    def invented(self) -> int:
        return sum(1 for o in self.outcomes if o.invented)

    @property
    def named_nothing(self) -> int:
        return sum(1 for o in self.outcomes if not o.citations and not o.unresolved)

    @property
    def accuracy(self) -> float:
        return self.reached / self.scored if self.scored else 0.0

    def render(self) -> str:
        lines = [
            f"{self.scored} rules questions, scored on whether the named provision",
            "reaches the text the question is about (D14's ceiling was 100%)",
            "",
            f"  reached          {self.accuracy:6.1%}  ({self.reached}/{self.scored})",
            f"  wrong provision  {self.mis_selected:>6}  (a real name, the wrong rule)",
            f"  invented a name  {self.invented:>6}  (resolves to nothing, degrades safely)",
            f"  named nothing    {self.named_nothing:>6}",
        ]
        misses = [o for o in self.outcomes if not o.reached]
        if misses:
            lines += ["", "misses:"]
            for outcome in misses:
                got = ", ".join(outcome.named) or ", ".join(outcome.unresolved) or "(nothing)"
                lines.append(f"  want {outcome.question.expected:<24} named {got[:44]!r}")
                lines.append(f"       {outcome.question.text[:70]}")
        return "\n".join(lines)


def score(
    caller: Caller,
    *,
    cba: sqlite3.Connection,
    league: sqlite3.Connection,
    questions: tuple[Question, ...] = tuple(RULES),
) -> Report:
    """
    Plan each question and check where its citation leads.

    Scored by containment, the same criterion D14 used: a plan naming §6(j) for
    a question about §6(j)(4)(i) has reached the right region, which is what
    the deterministic fetch then returns. Demanding the exact subsection would
    punish the 11 provisions that have no name of their own.
    """
    report = Report()
    for question in questions:
        try:
            built = plan(
                caller,
                question=question.text,
                kinds=(Kind.RULES,),
                cba=cba,
                league=league,
            )
        except JsonReplyError as exc:
            report.outcomes.append(
                Outcome(question, (), (), (), reached=False, error=str(exc)[:80])
            )
            continue

        target = ix.containing_chunk(cba, question.expected)
        passage = ix.fetch(cba, target[0], target[1]) if target else None
        reached = False
        if passage is not None:
            for citation in built.citations:
                body = " ".join(p.text for p in for_citation(cba, citation).passages)
                if passage.body[:120] in body:
                    reached = True
                    break
        report.outcomes.append(
            Outcome(
                question=question,
                named=built.named_as,
                citations=built.citations,
                unresolved=built.unresolved_names,
                reached=reached,
            )
        )
    return report
