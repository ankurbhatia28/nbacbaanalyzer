"""
Retrieval units (task 5.3).

A Section is the unit a lawyer would cite, and for most of the document it is
also the right size to retrieve: the median Section is about 1,500 characters.
But the distribution has a long tail — Art. VII §1 (Definitions) is 82,893
characters and §2 (Salary Cap) is 52,436 — so retrieving whole Sections would
hand back a chapter for a question about one sentence.

So a unit is a Section where that fits, and otherwise the Section is opened and
its subsections considered in turn, recursively. The split follows the
document's own numbering rather than a character window, which matters for two
reasons: every chunk keeps a citation someone can check, and no chunk begins or
ends mid-provision.

`MAX_CHARS` is a starting point, not a finding. D12 settles retrieval by
measurement, and task 5.8 is where this number gets chosen against recall@k
rather than asserted here.
"""

from __future__ import annotations

from dataclasses import dataclass

from .outline import Outline, Unit

MAX_CHARS = 4_000
"""Target ceiling for a retrieval unit. Revisited by the 5.8 eval."""


@dataclass(frozen=True, slots=True)
class Chunk:
    """One retrievable passage, with everything needed to cite and explain it."""

    citation: str
    heading_path: str
    """Ancestor titles, so a subsection carries the context it was read under."""
    text: str
    pdf_page: int
    printed_page: int
    last_pdf_page: int
    level: int
    oversized: bool = False
    """True when no further split was available and the unit still exceeds the
    ceiling. Flagged rather than force-cut, so a caller can see it."""

    @property
    def indexed_text(self) -> str:
        """
        What the index sees: the heading path followed by the body.

        A subsection reading "(i) Standard Traded Player Exception..." never
        says "Exceptions to the Salary Cap" or "Article VII", although that is
        how someone would search for it. Prepending the ancestors puts those
        terms in the unit that actually answers the question.
        """
        return f"{self.heading_path}\n{self.text}"

    @property
    def char_count(self) -> int:
        return len(self.text)


def _children(outline: Outline, parent: Unit) -> list[Unit]:
    """
    The units nested directly inside this one.

    Taken by span rather than by outline level: the outline flattens some
    levels, so "one level deeper" is not reliably "a child of this".
    """
    return [
        unit
        for unit in outline.units
        if parent.start < unit.start < parent.subtree_end
        and unit.level == _child_level(outline, parent)
    ]


def _child_level(outline: Outline, parent: Unit) -> int:
    """The shallowest level appearing strictly inside this unit's span."""
    inside = [
        unit.level
        for unit in outline.units
        if parent.start < unit.start < parent.subtree_end and unit.level > parent.level
    ]
    return min(inside) if inside else parent.level + 1


def _heading_path(outline: Outline, unit: Unit) -> str:
    """Ancestor titles from the Article down, so context travels with the text."""
    parts = []
    for candidate in outline.units:
        if candidate.start > unit.start:
            break
        if candidate.subtree_end >= unit.subtree_end and candidate.level < unit.level:
            parts.append(candidate.title)
    return " > ".join([*parts, unit.title])[:400]


def _split(outline: Outline, unit: Unit, max_chars: int, out: list[Chunk]) -> None:
    text = outline.subtree_text(unit)
    first, last = outline.page_range(unit)

    if len(text) <= max_chars:
        out.append(
            Chunk(
                citation=unit.citation,
                heading_path=_heading_path(outline, unit),
                text=text,
                pdf_page=first,
                printed_page=unit.printed_page,
                last_pdf_page=last,
                level=unit.level,
            )
        )
        return

    children = _children(outline, unit)
    if not children:
        # Nothing to split on. Emitted whole and flagged: cutting a provision
        # at a character count would produce a chunk no one can cite.
        out.append(
            Chunk(
                citation=unit.citation,
                heading_path=_heading_path(outline, unit),
                text=text,
                pdf_page=first,
                printed_page=unit.printed_page,
                last_pdf_page=last,
                level=unit.level,
                oversized=True,
            )
        )
        return

    # The parent's own preamble -- the text before its first child -- is kept,
    # because it often carries the condition the subsections operate under
    # ("Subject to the rules set forth in Section 2(e) above...").
    preamble = outline.text[unit.start : children[0].start].strip()
    if preamble:
        out.append(
            Chunk(
                citation=unit.citation,
                heading_path=_heading_path(outline, unit),
                text=preamble,
                pdf_page=first,
                printed_page=unit.printed_page,
                last_pdf_page=first,
                level=unit.level,
                # A preamble has no sub-structure in the outline, so when it
                # alone exceeds the ceiling there is nothing to split it on --
                # the same case as a childless unit, and flagged the same way.
                oversized=len(preamble) > max_chars,
            )
        )
    for child in children:
        _split(outline, child, max_chars, out)


def build(outline: Outline, max_chars: int = MAX_CHARS) -> list[Chunk]:
    """
    Every Section, split down to subsections wherever it is too large.

    Articles are not emitted as units: an Article is tens of thousands of
    characters and would be split into its Sections anyway, so starting at the
    Section avoids producing the same text twice at two granularities.
    """
    out: list[Chunk] = []
    for section in outline.sections():
        _split(outline, section, max_chars, out)
    return out
