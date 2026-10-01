"""
The cross-reference graph (task 5.5).

The CBA is written as a network, not a list. Art. VII §6(j) opens "Subject to
the rules set forth in Section 2(e) above", and §2(e) is where the apron
restrictions live -- so retrieving §6(j) alone hands back an exception without
the precondition that governs it. The text makes 1,144 bare Section references
and 337 that name their Article explicitly.

Resolution needs the referring unit's context. A bare "Section 6(j)" means
Section 6(j) *of the Article it appears in*; the same string in two Articles
points at two different provisions. That is why references are extracted per
unit rather than over the document as a whole.

Targets are checked against the outline. A reference that resolves to nothing
is counted and kept for inspection rather than quietly dropped -- it means
either the parser is wrong or the document points somewhere the outline does
not reach, and both are worth knowing.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from .outline import Outline, Unit

_MARKERS = r"(?:\([A-Za-z0-9]{1,5}\))*"

_REFERENCE = re.compile(
    # Named Article first, so "Article VII, Section 6(j)" is not read as a bare
    # Section reference to whichever Article happens to be enclosing.
    rf"(?:Article\s+(?P<article>[IVXLC]+),?\s+)?"
    rf"Section\s+(?P<section>\d+)(?P<markers>{_MARKERS})"
)

_EXTERNAL = re.compile(
    r"\s*of\s+(?:the\s+)?(?:[A-Z][\w.'-]*\s+){0,6}(?:Code|Act|Act\s+of\s+\d{4})\b"
)
"""
A reference to a statute rather than to this Agreement.

Article IV cites the Internal Revenue Code constantly -- "Section 401(a) of
the Code", "Section 415(d)(2) of the Code" -- and Article VI cites "Section
302(c)(5) of the Labor Management Relations Act of 1947". Read as internal
references these produced 44 edges to provisions that do not exist, which is
how they were found: every one of them failed to resolve.
"""


@dataclass(frozen=True, slots=True)
class Reference:
    """One pointer from one provision to another."""

    source: str
    target: str
    raw: str
    explicit_article: bool
    """Whether the text named the Article or relied on context."""
    resolved: bool = True
    """False when `target` names a provision the outline does not contain."""


@dataclass
class Graph:
    out: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    into: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    references: list[Reference] = field(default_factory=list)
    unresolved: list[Reference] = field(default_factory=list)
    """References whose target is not a unit in the outline."""

    def add(self, reference: Reference) -> None:
        """
        Record a reference. Unresolved ones are kept aside, not edged.

        An edge to a provision that does not exist would send retrieval after
        nothing, but discarding the reference entirely would hide the fact that
        the parser or the document disagreed with the outline.
        """
        if not reference.resolved:
            self.unresolved.append(reference)
            return
        self.references.append(reference)
        self.out[reference.source].add(reference.target)
        self.into[reference.target].add(reference.source)

    def expand(self, citations: list[str], hops: int = 1) -> list[str]:
        """
        The seeds plus what they point at, breadth-first.

        One hop by default. Two hops reaches most of Article VII from almost
        anywhere in it, which stops being context and starts being the whole
        Article -- the opposite of what retrieval is for.

        Order is preserved so the caller can tell a seed from an expansion: the
        seeds come first, in the order given.
        """
        seen = list(dict.fromkeys(citations))
        frontier = list(seen)
        for _ in range(hops):
            nxt: list[str] = []
            for citation in frontier:
                for target in sorted(self.out.get(citation, ())):
                    if target not in seen:
                        seen.append(target)
                        nxt.append(target)
            frontier = nxt
            if not frontier:
                break
        return seen

    def cited_by(self, citation: str) -> list[str]:
        """
        Which provisions point *here*.

        Useful in the other direction: a definition or a restriction is often
        best explained by what relies on it.
        """
        return sorted(self.into.get(citation, ()))


def references_in(outline: Outline, unit: Unit, text: str) -> list[Reference]:
    """
    Every provision this text points at.

    Self-references are discarded: a provision citing its own number is
    describing itself, and an edge from a node to itself tells retrieval
    nothing.
    """
    found: list[Reference] = []
    seen: set[str] = set()
    for match in _REFERENCE.finditer(text):
        article = match.group("article") or unit.article
        if not article:
            continue
        if _EXTERNAL.match(text, match.end()):
            continue
        section = match.group("section") + (match.group("markers") or "")
        target, attempted = _canonical(outline, article.upper(), section)
        citation = target or attempted
        if citation == unit.citation or citation in seen:
            continue
        seen.add(citation)
        found.append(
            Reference(
                source=unit.citation,
                target=citation,
                raw=match.group(0),
                explicit_article=bool(match.group("article")),
                resolved=target is not None,
            )
        )
    return found


def _canonical(outline: Outline, article: str, section: str) -> tuple[str | None, str]:
    """
    The citation string for a reference, if the outline has that provision.

    Falls back through the ancestors the way `Outline.resolve` does, because the
    document cites subsections the PDF never bookmarked -- a reference to
    §8(e)(1) should still reach §8 rather than being thrown away.
    """
    unit, used = outline.resolve(article, section)
    return (used if unit is not None else None), used


def build(outline: Outline) -> Graph:
    """
    Walk every unit and record what it points at.

    Scanned over each unit's *own* text rather than its subtree, so an edge is
    attributed to the provision that actually contains the words. Using the
    subtree would credit a Section with every reference made by its
    subsections.
    """
    graph = Graph()
    for unit in outline.units:
        body = outline.own_text(unit)
        if not body:
            continue
        for reference in references_in(outline, unit, body):
            graph.add(reference)
    return graph
