"""
Retrieval evals (task 5.8).

Fifty questions with the provision each one should reach, scored on recall@k
and on whether the top hit is the right passage. The point is to settle two
things that were asserted rather than measured: whether BM25 alone is good
enough (D12), and what `chunks.MAX_CHARS` should be.

**Where the expectations come from matters more than the number of them.**
Writing both the question and its answer invites a set that flatters whatever
the retriever already does. Two things guard against that here:

* The expected citations are not chosen freely. Every one comes from a source
  already verified against the document -- the 30 engine citations that task
  5.2a checked provision by provision, and the definitions index, whose
  term-to-citation mapping is extracted from the text rather than recalled.
* The questions are written as a user would ask them, not in the provision's
  own words. "How much salary can a team take back when it trades a player"
  does not contain "Traded Player Exception", so BM25 is not handed the answer.

What this still cannot measure is whether a real user would phrase a question
the way I did. That needs questions from someone else, and it is recorded as a
limitation rather than papered over.

**Scoring credits containment, not string equality.** A question about
§6(j)(1)(i) is answered correctly by the chunk for §6(j)(1), because that chunk
contains the provision -- chunks stop splitting once a passage fits the
ceiling. Demanding an exact citation match would mark right answers wrong and
would make the score an artefact of the chunk ceiling.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from enum import StrEnum

from .index import containing_chunk, search


class Kind(StrEnum):
    """
    How a question is phrased, which turns out to be the whole story.

    Reported separately because the aggregate hides the finding: BM25 does
    reasonably when the query carries the term of art and collapses when it
    does not, so a single number would be an average over two different
    situations.
    """

    PARAPHRASE = "paraphrased, no term of art"
    TERM = "contains the term of art"


@dataclass(frozen=True, slots=True)
class Question:
    """One question and the provision it should reach."""

    text: str
    expected: str
    """A citation, verified against the document rather than recalled."""
    source: str
    """Where the expectation comes from, so it can be re-checked."""
    kind: Kind = Kind.PARAPHRASE


# -- rules questions -------------------------------------------------------
#
# Expected citations are the engine's, each verified in 5.2a to point inside
# its own provision. Phrased as a user would ask, not as the CBA words it.

RULES: list[Question] = [
    Question(
        "How much salary can a team take back when it trades one player away?",
        "Art. VII §6(j)(1)(i)",
        "engine.citations.TPE_STANDARD",
    ),
    Question(
        "Can a team put two contracts together to bring back one bigger salary?",
        "Art. VII §6(j)(1)(ii)",
        "engine.citations.TPE_AGGREGATED",
    ),
    Question(
        "Is there a larger allowance for matching salary in a trade, and what is it worth?",
        "Art. VII §6(j)(1)(iv)",
        "engine.citations.TPE_EXPANDED",
    ),
    Question(
        "If a team is under the cap, can it absorb salary without an exception?",
        "Art. VII §6(j)(1)(v)",
        "engine.citations.TPE_ROOM",
    ),
    Question(
        "How long after acquiring a player must a team wait before combining his contract "
        "with another in a trade?",
        "Art. VII §6(j)(4)(i)",
        "engine.citations.AGGREGATION_TWO_MONTH_BAR",
    ),
    Question(
        "Is there a cap on how many contracts can be combined at once?",
        "Art. VII §6(j)(4)(ii)",
        "engine.citations.AGGREGATION_THREE_PLAYER_RULE",
    ),
    Question(
        "What transactions is a team barred from making once its payroll is too high?",
        "Art. VII §2(e)(2)(i)(A)",
        "engine.citations.TRANSACTION_PROHIBITION",
    ),
    Question(
        "After a team does one of the restricted transactions, what ceiling applies to it "
        "for the rest of the year?",
        "Art. VII §2(e)(2)(i)(B)",
        "engine.citations.TRANSACTION_RESTRICTIONS",
    ),
    Question(
        "Which specific transactions trigger a spending ceiling, and at which level?",
        "Art. VII §2(e)(4)",
        "engine.citations.TRANSACTION_RESTRICTIONS_TABLE",
    ),
    Question(
        "What are the two apron levels set at?",
        "Art. VII §2(a)(4)(iii)",
        "engine.citations.APRON_LEVELS",
    ),
    Question(
        "How is the payroll figure used for apron purposes worked out?",
        "Art. VII §2(e)(1)",
        "engine.citations.APRON_TEAM_SALARY",
    ),
    Question(
        "If a restricted transaction happens after the season ends, which year does the "
        "limit bind?",
        "Art. VII §2(e)(2)(ii)",
        "engine.citations.SUBSEQUENT_YEAR_RESTRICTION",
    ),
    Question(
        "What draft pick penalty applies to the highest-spending teams?",
        "Art. VII §2(f)",
        "engine.citations.DRAFT_PICK_PENALTY",
    ),
    Question(
        "What is the mid-level exception for a team that is not paying the tax?",
        "Art. VII §6(e)",
        "engine.citations.NON_TAXPAYER_MLE",
    ),
    Question(
        "How much can a tax-paying team offer with its mid-level?",
        "Art. VII §6(f)",
        "engine.citations.TAXPAYER_MLE",
    ),
    Question(
        "Do some exceptions require a team to be close to the cap before using them?",
        "Art. VII §6(n)",
        "engine.citations.TPE_ALLOWANCE_REMOVED_AT_APRON",
    ),
    Question(
        "Can a team send money to another team as part of a deal?",
        "Art. VII §8(a)",
        "engine.citations.CASH_IN_TRADE",
    ),
    Question(
        "What are the rules on trading players generally?",
        "Art. VII §8",
        "engine.citations.TRADE_RULES",
    ),
    Question(
        "How does signing a player and immediately dealing him work?",
        "Art. VII §8",
        "engine.citations.SIGN_AND_TRADE, widened: the PDF does not bookmark §8(e), "
        "so the containing Section is the finest scoreable target (see 5.2b)",
    ),
    Question(
        "When a young player's extension is dealt, how is his number counted?",
        "Art. VII §8(g)",
        "engine.citations.ROOKIE_EXTENSION_TRADE_RULE",
    ),
    Question(
        "What can a team offer a restricted free agent who has only played one or two years?",
        "Art. XI §5(d)(i)",
        "engine.citations.ARENAS_OFFER_SHEET_LIMIT",
    ),
    Question(
        "How is a balloon payment in the third year of an offer sheet handled?",
        "Art. XI §5(d)(ii)",
        "engine.citations.ARENAS_THIRD_YEAR",
    ),
    Question(
        "When an offer sheet is matched, what figure counts for the matching team?",
        "Art. XI §5(d)(iii)",
        "engine.citations.ARENAS_DEEMED_AVERAGE",
    ),
    Question(
        "Which awards let a player qualify for a higher maximum?",
        "Art. II §7",
        "engine.citations.HIGHER_MAX_CRITERIA",
    ),
    Question(
        "What honors count toward a player's eligibility for a bigger deal?",
        "Art. I §1(cc)",
        "engine.citations.GENERALLY_RECOGNIZED_HONORS",
    ),
]


# -- definition questions -------------------------------------------------
#
# Generated from the definitions index, whose term-to-citation mapping is
# extracted from the document. A user asking about a term of art does use the
# term, so including it in the question is realistic rather than a giveaway.

DEFINITION_TERMS: list[str] = [
    "Apron Team Salary",
    "Traded Player",
    "Replacement Player",
    "Years of Service",
    "Base Compensation",
    "Early Termination Option",
    "Maximum Annual Salary",
    "Minimum Annual Salary",
    "Qualifying Offer",
    "Restricted Free Agent",
    "Designated Veteran Player",
    "Rookie Salary Scale",
    "Salary Cap",
    "Team Salary",
    "Tax Team Salary",
    "Free Agent",
    "Renegotiation",
    "Force Majeure Event",
    "Exception",
    "Unlikely Bonus",
    "Performance Bonus",
    "Two-Way Contract",
    "Active List",
    "Audit Report",
    "Basketball Related Income",
]
"""
Terms to ask about. Chosen for being the ones the engine reasons over, not for
being easy to find. Any term not present in the built index is reported by the
harness rather than skipped -- a missing term means the definitions parser
regressed.
"""


def definition_questions(conn: sqlite3.Connection) -> list[Question]:
    """
    Build "what does X mean" questions from the index's own definitions.

    The expected citation is read out of the artifact, so it cannot drift from
    what the parser actually extracted.
    """
    from .index import definition_for

    out: list[Question] = []
    for term in DEFINITION_TERMS:
        definition = definition_for(conn, term)
        if definition is None:
            continue
        out.append(
            Question(
                f"What does {term} mean?",
                definition.citation,
                f"definitions index: {definition.term}",
                Kind.TERM,
            )
        )
    return out


def missing_terms(conn: sqlite3.Connection) -> list[str]:
    """Terms the index cannot explain. Reported, because it means a regression."""
    from .index import definition_for

    return [term for term in DEFINITION_TERMS if definition_for(conn, term) is None]


# -- scoring ---------------------------------------------------------------

CUTOFFS = (1, 3, 5, 10)


@dataclass(frozen=True, slots=True)
class Result:
    question: Question
    rank: int | None
    """1-based rank of the passage containing the expected provision, or None."""
    top: str | None
    expected_chunk: tuple[str, int] | None

    @property
    def found(self) -> bool:
        return self.rank is not None

    @property
    def exact_at_one(self) -> bool:
        """
        Whether the top hit is the chunk that holds the expected provision.

        Not whether its citation string matches: a question about §6(j)(1)(i)
        is answered by the chunk for §6(j)(1), which contains it.
        """
        return self.rank == 1


@dataclass
class Report:
    results: list[Result] = field(default_factory=list)
    unmapped: list[Question] = field(default_factory=list)
    """
    Questions whose expected citation is not in the index at all.

    A failure of the harness, not of retrieval, and kept separate so it cannot
    be mistaken for a recall problem.
    """
    missing_terms: list[str] = field(default_factory=list)
    max_chars: int = 0

    def subset(self, kind: Kind) -> Report:
        """The same report restricted to one phrasing, for the split."""
        return Report(
            results=[r for r in self.results if r.question.kind is kind],
            max_chars=self.max_chars,
        )

    @property
    def scored(self) -> int:
        return len(self.results)

    def recall_at(self, k: int) -> float:
        if not self.results:
            return 0.0
        hit = sum(1 for r in self.results if r.rank is not None and r.rank <= k)
        return hit / len(self.results)

    @property
    def mrr(self) -> float:
        """
        Mean reciprocal rank. Rewards putting the right passage first rather
        than merely somewhere in the list, which recall@10 cannot distinguish.
        """
        if not self.results:
            return 0.0
        return sum(1 / r.rank for r in self.results if r.rank) / len(self.results)

    def render(self) -> str:
        lines = [
            f"{self.scored} questions scored, ceiling {self.max_chars} chars",
            "",
        ]
        for k in CUTOFFS:
            lines.append(f"  recall@{k:<3} {self.recall_at(k):6.1%}")
        lines.append(f"  MRR       {self.mrr:6.3f}")

        lines += ["", "by how the question is phrased:"]
        header = f"  {'':<28} {'n':>3} {'r@1':>7} {'r@3':>7} {'r@10':>7} {'MRR':>6}"
        lines.append(header)
        for kind in Kind:
            part = self.subset(kind)
            if not part.results:
                continue
            lines.append(
                f"  {kind.value:<28} {part.scored:>3} {part.recall_at(1):>7.1%} "
                f"{part.recall_at(3):>7.1%} {part.recall_at(10):>7.1%} {part.mrr:>6.3f}"
            )
        misses = [r for r in self.results if not r.found]
        if misses:
            lines += ["", f"not found in the top {max(CUTOFFS)}:"]
            lines += [f"  {r.question.expected:<24} {r.question.text[:62]}" for r in misses[:12]]
        if self.unmapped:
            lines += ["", "expected citation absent from the index (harness fault):"]
            lines += [f"  {q.expected}  <- {q.source}" for q in self.unmapped]
        if self.missing_terms:
            lines += ["", f"terms the index cannot explain: {', '.join(self.missing_terms)}"]
        return "\n".join(lines)


def score(conn: sqlite3.Connection, questions: list[Question], depth: int = 10) -> Report:
    """
    Run every question and record where the right passage landed.

    Scored on search alone, deliberately. Cross-reference expansion and
    definition attachment make an answer more useful but they also make it
    impossible to tell whether the query found the provision or merely found
    something that pointed at it -- and only the first is retrieval working.
    """
    report = Report(max_chars=0)
    for question in questions:
        target = containing_chunk(conn, question.expected)
        if target is None:
            report.unmapped.append(question)
            continue
        hits = search(conn, question.text, limit=depth)
        rank = None
        for position, hit in enumerate(hits, start=1):
            if (hit.citation, hit.ordinal) == target:
                rank = position
                break
        report.results.append(
            Result(
                question=question,
                rank=rank,
                top=hits[0].label if hits else None,
                expected_chunk=target,
            )
        )
    report.missing_terms = missing_terms(conn)
    return report


def all_questions(conn: sqlite3.Connection) -> list[Question]:
    return [*RULES, *definition_questions(conn)]


# -- the ceiling study ----------------------------------------------------


def sweep(
    outline: object,
    caps: tuple[int, ...] = (1_000, 2_000, 3_000, 4_000, 6_000, 10_000),
) -> list[Report]:
    """
    Score the golden set at several chunk ceilings (task 5.3's open parameter).

    Built fresh at each ceiling rather than re-querying one index, because the
    ceiling changes what a chunk *is* -- there is no way to simulate it.

    Note the metric's bias: credit goes to the chunk containing the expected
    provision, so a coarser ceiling is structurally favoured. recall@1 and MRR
    do not reward coarseness, which is why they decide.
    """
    from . import index as ix
    from .chunks import build as build_chunks
    from .crossrefs import build as build_graph
    from .definitions import build as build_definitions
    from .outline import Outline

    assert isinstance(outline, Outline)
    import tempfile
    from pathlib import Path

    definitions = build_definitions(outline)
    graph = build_graph(outline)
    out: list[Report] = []
    for cap in caps:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sweep.db"
            ix.build(path, build_chunks(outline, max_chars=cap), definitions, graph, outline)
            conn = ix.open_index(path)
            report = score(conn, all_questions(conn))
            report.max_chars = cap
            out.append(report)
    return out


def render_sweep(reports: list[Report]) -> str:
    lines = [
        f"  {'ceiling':>8} {'n':>4} {'r@1':>7} {'r@3':>7} {'r@10':>7} {'MRR':>6}",
    ]
    best = max(reports, key=lambda r: (r.mrr, r.recall_at(1)))
    for report in reports:
        marker = " <- chosen" if report is best else ""
        lines.append(
            f"  {report.max_chars:>8} {report.scored:>4} {report.recall_at(1):>7.1%} "
            f"{report.recall_at(3):>7.1%} {report.recall_at(10):>7.1%} {report.mrr:>6.3f}{marker}"
        )
    return "\n".join(lines)


# -- option A: resolving a question to a name, then looking it up ---------


@dataclass
class NamedLookupReport:
    """
    How far D14 option A can go: the agent names a provision, we look it up.

    Scored separately from search because it is not search. The question is
    whether the document's own vocabulary can *reach* every provision the
    engine cites, which bounds what intent extraction can achieve -- it does
    not measure whether a model picks the right name, which cannot be known
    offline.
    """

    exact: int = 0
    """Provisions with a heading or defined term of their own."""
    via_ancestor: int = 0
    """Provisions with no name, reached by naming the one that contains them."""
    unnameable: int = 0
    reached: int = 0
    """Where the deterministic lookup returned text containing the target."""
    total: int = 0
    mean_chars: int = 0
    misses: list[tuple[str, str]] = field(default_factory=list)

    @property
    def reach(self) -> float:
        return self.reached / self.total if self.total else 0.0

    def render(self) -> str:
        lines = [
            f"{self.total} provisions the engine cites, resolved by name:",
            f"  named directly        {self.exact:>3}",
            f"  named via an ancestor {self.via_ancestor:>3}",
            f"  unnameable            {self.unnameable:>3}",
            "",
            f"  deterministic lookup returned the target: {self.reached}/{self.total} "
            f"= {self.reach:.0%}  (mean {self.mean_chars:,} chars)",
        ]
        if self.misses:
            lines += ["", "did not reach the target:"]
            lines += [f"  {cite:<24} named {name!r}" for cite, name in self.misses]
        return "\n".join(lines)


def score_named_lookup(conn: sqlite3.Connection) -> NamedLookupReport:
    """
    Resolve each rules question by name instead of searching for it.

    This is the measurement that settled D14. Searching with a paraphrase
    reaches the right provision 20% of the time at recall@3; naming it and
    looking it up reaches it every time.
    """
    from .index import fetch, nameable_ancestor, resolve_term
    from .retrieve import for_citation

    report = NamedLookupReport()
    chars = 0
    for question in RULES:
        report.total += 1
        name = nameable_ancestor(conn, question.expected)
        if name is None:
            report.unnameable += 1
            report.misses.append((question.expected, "no name in the vocabulary"))
            continue
        resolved = resolve_term(conn, name)
        if resolved is None:
            report.unnameable += 1
            continue
        citation, _ = resolved
        if citation == question.expected:
            report.exact += 1
        else:
            report.via_ancestor += 1

        result = for_citation(conn, citation)
        body = " ".join(p.text for p in result.passages)
        chars += len(body)
        target = containing_chunk(conn, question.expected)
        passage = fetch(conn, target[0], target[1]) if target else None
        if passage is not None and passage.body[:120] in body:
            report.reached += 1
        else:
            report.misses.append((question.expected, name))
    report.mean_chars = chars // report.total if report.total else 0
    return report
