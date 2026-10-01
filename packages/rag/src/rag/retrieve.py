"""
Retrieval, composed (tasks 5.5, 5.7, 5.9).

Three things happen here that searching alone does not do.

**One-hop expansion.** Art. VII §6(j)(1)(i) opens "Subject to the rules set
forth in Section 2(e) above". A reader given only the exception has been given
a permission with its precondition removed, so what a passage points at comes
back with it.

**Definitions attached.** The terms Article I fixes govern every other Article,
and a passage that turns on what "Apron Team Salary" means is not
self-contained without it.

**Provenance on every passage.** Each one records *why* it is in the result --
matched the query, cited by something that did, or fetched by citation. A
reader has to be able to tell the passage that answered the question from the
context dragged in behind it, and so does the agent: only the first kind is
evidence that the question was understood.

Task 5.7 is `for_citation`: a violation code names a provision and the text
comes back by lookup, with no search and no ranking involved. The model quotes
it; it never chooses it.

Task 5.9 is `figures_in`. Retrieved prose is full of numbers -- "$250,000",
"125%", "$7,500,000" -- and almost all of them are from a prior CBA, an
example, or a different exception than the one asked about. A number that
reaches a user must come from a tool result, so passages are marked with the
figures they contain and the agent is forbidden to read an answer out of them.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from enum import StrEnum

from .index import (
    Hit,
    StoredDefinition,
    all_definition_names,
    chunks_within,
    definition_for,
    fetch,
    fetch_nearest,
    search,
)


class Why(StrEnum):
    """How a passage came to be in the result."""

    MATCHED = "matched the query"
    REFERENCED = "referenced by a matching passage"
    CITED = "fetched by citation"


@dataclass(frozen=True, slots=True)
class Passage:
    label: str
    citation: str
    text: str
    pdf_page: int
    printed_page: int
    why: Why
    score: float | None = None
    """BM25 for a match, None for anything pulled in as context."""
    referenced_by: str | None = None

    @property
    def is_evidence(self) -> bool:
        """
        Whether this passage answered the question or merely accompanies one.

        Context is not evidence. An answer resting only on expansion means the
        query never actually matched the provision it claims to rely on.
        """
        return self.why is Why.MATCHED


@dataclass
class Retrieval:
    query: str
    passages: list[Passage] = field(default_factory=list)
    definitions: list[StoredDefinition] = field(default_factory=list)
    figures: list[str] = field(default_factory=list)
    """
    Numbers appearing in the retrieved prose (task 5.9).

    Present so they can be refused, not used. Any figure a user sees must come
    from a tool result.
    """
    resolved_to: str | None = None
    """
    For a citation lookup, the provision actually returned.

    Set only when it differs from what was asked for, which happens when the
    citation is finer-grained than any chunk. The caller must cite this rather
    than the request.
    """

    @property
    def evidence(self) -> list[Passage]:
        return [p for p in self.passages if p.is_evidence]

    @property
    def citations(self) -> list[str]:
        return [p.label for p in self.passages]

    def render(self) -> str:
        lines = [f"query: {self.query}", ""]
        for passage in self.passages:
            marker = "*" if passage.is_evidence else " "
            suffix = f" <- {passage.referenced_by}" if passage.referenced_by else ""
            lines.append(f" {marker} {passage.label} (p.{passage.pdf_page}){suffix}")
        if self.definitions:
            lines += ["", "defined terms:"]
            lines += [f"   {d.term} - {d.citation}" for d in self.definitions]
        if self.figures:
            lines += [
                "",
                f"figures in this prose ({len(self.figures)}): must not be answered from — "
                "a number reaching the user comes from a tool result (5.9)",
            ]
        return "\n".join(lines)


EXPANSION_PER_HIT = 2
"""At most this many referenced provisions per matching passage."""

EXPANSION_BUDGET = 4
"""And at most this many across the whole result."""

SECTION_PREAMBLE_CHARS = 400
"""
Below this, a cited provision is treated as a heading rather than an answer.

"(e) Operation of Apron Levels." is 30 characters and "Section 8. Trade Rules."
is 23 -- returning either as the text of the provision would be a lookup that
reports success and conveys nothing.
"""

INNER_PASSAGES = 5
"""
How many subsections to return for a citation finer than a whole Section.

Rarely needed: a specific subsection resolves to the chunk containing it.
"""

SECTION_INNER_PASSAGES = 12
"""
How many to return when the citation names a whole Section.

This is the case that needs breadth, and only this one. Eleven of the 25
provisions the engine cites have no heading of their own, so naming them (D14
option A) reaches a whole Section instead -- "trade rules" for §8(g), the
rookie-extension rule. At 5 subsections the target was missed 2 times in 25; at
12 it is never missed, which is worth the extra text *here* while not inflating
every lookup, since a lookup that already names the subsection needs none of it.

Measured over the 25 rules questions, naming each one's nearest named
provision: 5 -> 92% reach at 4.5k characters, 8 -> 96% at 7.0k, 12 -> 100% at
9.6k.
"""


_FIGURE = re.compile(
    r"""
    \$\s?[\d,]+(?:\.\d+)?            # $250,000
  | \b\d+(?:\.\d+)?\s?%              # 125%
  | \b\d{1,3}(?:,\d{3})+\b           # 7,500,000
    """,
    re.X,
)


def figures_in(text: str) -> list[str]:
    """
    Every number in a passage that could be mistaken for an answer.

    Deliberately broad. The cost of flagging a figure that was never going to
    be quoted is nothing; the cost of missing one is a confident wrong dollar
    amount, which is the failure this project exists to prevent.
    """
    return list(dict.fromkeys(match.group(0).strip() for match in _FIGURE.finditer(text)))


def _passage(hit: Hit, why: Why, referenced_by: str | None = None) -> Passage:
    return Passage(
        label=hit.label,
        citation=hit.citation,
        text=hit.body,
        pdf_page=hit.pdf_page,
        printed_page=hit.printed_page,
        why=why,
        score=hit.score if why is Why.MATCHED else None,
        referenced_by=referenced_by,
    )


def _definitions_for(conn: sqlite3.Connection, text: str, limit: int) -> list[StoredDefinition]:
    """
    The defined terms a body of text uses, longest match first.

    Matched against the names held in the artifact rather than re-deriving
    them, and case-sensitively, because the document capitalises a term where
    it carries its defined meaning.
    """
    out: list[StoredDefinition] = []
    seen: set[str] = set()
    consumed: list[tuple[int, int]] = []
    for name in all_definition_names(conn):
        if len(out) >= limit:
            break
        for match in re.finditer(rf"\b{re.escape(name)}\b", text):
            span = match.span()
            if any(a <= span[0] and span[1] <= b for a, b in consumed):
                continue
            consumed.append(span)
            if name.lower() in UNINFORMATIVE:
                break
            definition = definition_for(conn, name)
            if definition and definition.term not in seen:
                seen.add(definition.term)
                out.append(definition)
            break
    return out


UNINFORMATIVE = frozenset(
    {
        "team",
        "nba team",
        "member",
        "agreement",
        "season",
        "regular season",
        "contract",
        "player contract",
        "uniform player contract",
        "salary cap year",
    }
)
"""
Terms too common to be worth attaching. Mirrors `definitions.UBIQUITOUS`, held
lowercase because this match happens against the stored names.
"""


def retrieve(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 5,
    expand: bool = True,
    definitions: int = 4,
) -> Retrieval:
    """
    Search, then bring in what the matches depend on.

    Expansion is capped at one hop. Two reaches most of Article VII from
    almost anywhere inside it, which stops being context and becomes the
    whole Article.
    """
    result = Retrieval(query=query)
    hits = search(conn, query, limit=limit)
    seen = {(hit.citation, hit.ordinal) for hit in hits}
    for hit in hits:
        result.passages.append(_passage(hit, Why.MATCHED))

    if expand:
        from .index import targets_of

        # Capped per hit and overall. The Transaction Restrictions Table alone
        # cites eight provisions, and without a cap one broad match buries the
        # passages that actually answered the question.
        budget = EXPANSION_BUDGET
        for hit in hits:
            if budget <= 0:
                break
            added = 0
            for target in targets_of(conn, hit.citation):
                if added >= EXPANSION_PER_HIT or budget <= 0:
                    break
                if (target, 1) in seen:
                    continue
                referenced = fetch(conn, target)
                if referenced is None:
                    continue
                seen.add((target, 1))
                result.passages.append(_passage(referenced, Why.REFERENCED, hit.label))
                added += 1
                budget -= 1

    body = " ".join(p.text for p in result.passages)
    result.definitions = _definitions_for(conn, body, definitions)
    result.figures = figures_in(body)
    return result


def for_citation(
    conn: sqlite3.Connection, citation: str, *, ordinal: int = 1, definitions: int = 4
) -> Retrieval:
    """
    The text of one provision, by lookup (task 5.7).

    The deterministic half of retrieval. A violation code resolves to a
    citation and the citation resolves to text; no ranking, no model, nothing
    that can return the wrong provision because a query was phrased oddly.
    Returns an empty result rather than a near miss when the citation is not
    in the index -- a plausible substitute is worse than nothing here.
    """
    result = Retrieval(query=citation)
    if ordinal != 1:
        hit, used = fetch(conn, citation, ordinal=ordinal), citation
    else:
        hit, used = fetch_nearest(conn, citation)
    if hit is None:
        return result
    if used != citation:
        result.resolved_to = used
    result.passages.append(_passage(hit, Why.CITED))

    # A citation naming a split Section resolves to its preamble, which is
    # frequently just the heading. The substance is in the subsections, so they
    # come too -- otherwise the deterministic path "succeeds" with 23
    # characters of title.
    if len(hit.body) < SECTION_PREAMBLE_CHARS:
        breadth = INNER_PASSAGES if "(" in used else SECTION_INNER_PASSAGES
        for inner in chunks_within(conn, used, limit=breadth):
            if (inner.citation, inner.ordinal) == (hit.citation, hit.ordinal):
                continue
            result.passages.append(_passage(inner, Why.CITED, hit.label))

    body = " ".join(p.text for p in result.passages)
    result.definitions = _definitions_for(conn, body, definitions)
    result.figures = figures_in(body)
    return result
