"""
The CBA's structure, taken from the document rather than guessed at (tasks 5.1, 5.2).

The PDF carries a 2,412-entry bookmark outline: 42 Articles, 288 Sections, 938
subsections and four deeper levels. That is the document's own table of
structure, authored by whoever produced the PDF, so traversing it beats any
heuristic that re-derives headings from font sizes or numbering patterns. A
regex looking for "Section 6." finds the Table of Contents too; the outline
knows the difference.

Two things make the traversal non-trivial, and both are handled here.

**Locating a unit's text.** The outline gives a page, not an offset, and a page
holds many units -- every definition in Article I Section 1 starts on page 25.
So each entry is located by searching for its title inside the document text,
starting from its own page so that an identical string in the Table of Contents
cannot match first. Titles are truncated at 254 characters and the long ones
run past a page break, so the search uses a normalised 40-character prefix:
that matches 2,411 of 2,412 entries, where the full title matches 1,069.

**Page numbers.** The pages carry a printed folio that runs 24 behind the PDF
page (PDF 25 is printed page 1), confirmed on 560 of the 563 pages where a
folio is machine-readable. Both numbers are kept on every unit, because a
citation that says "p. 211" is ambiguous and wrong half the time: the existing
`engine.citations` values are PDF pages.
"""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

import pymupdf

DEFAULT_PDF = Path(__file__).resolve().parents[4] / "data" / "cba" / "nba-cba-2023.pdf"

PRINTED_PAGE_OFFSET = 24
"""PDF page minus this gives the folio printed on the page."""

PREFIX_CHARS = 40
"""
How much of a title to match on.

Long enough to be unique in practice, short enough to survive a title that was
truncated at 254 characters or that wraps across a page break. Measured: 40
characters matches 2,411 of 2,412 entries; the full title matches 1,069.
"""

_ARTICLE = re.compile(r"^Article\s+([IVXLC]+)\b", re.I)
_SECTION = re.compile(r"^Section\s+(\d+)\b", re.I)
_SUBSECTION = re.compile(r"\(([A-Za-z0-9]+)\)")
_LEADING_MARKERS = re.compile(r"^\s*((?:\([A-Za-z0-9]{1,5}\)\s*)+)")


def normalise(text: str) -> str:
    """
    Collapse whitespace.

    The PDF hard-wraps every line, so the raw text is full of breaks that mean
    nothing. Collapsing them makes a unit readable when quoted back to a user
    and gives the index whole words rather than hyphenated fragments.
    """
    return re.sub(r"\s+", " ", text).strip()


@dataclass(frozen=True, slots=True)
class Unit:
    """One node of the outline, with the text that belongs to it."""

    index: int
    level: int
    title: str
    pdf_page: int
    start: int
    """Offset into the document text where this unit's own text begins."""
    own_end: int
    """Where the next unit of any level begins."""
    subtree_end: int
    """Where the next unit at this level or higher begins; includes descendants."""
    article: str | None = None
    section: str | None = None
    subsection: tuple[str, ...] = ()

    @property
    def printed_page(self) -> int:
        return self.pdf_page - PRINTED_PAGE_OFFSET

    @property
    def citation(self) -> str:
        """
        How this unit would be cited, e.g. "Art. VII §6(j)(1)(i)".

        Built from the outline's own numbering, so it cannot drift from the
        document the way a hand-maintained table would.
        """
        if self.article is None:
            return self.title[:60]
        out = f"Art. {self.article}"
        if self.section:
            out += f" §{self.section}"
            out += "".join(f"({part})" for part in self.subsection)
        return out


@dataclass
class Outline:
    """The whole document: its text, its units, and the index over them."""

    text: str
    units: list[Unit]
    page_starts: list[int] = field(default_factory=list)
    unmatched: list[tuple[int, str, int]] = field(default_factory=list)
    """Entries whose text could not be located. Reported, never dropped."""

    def page_range(self, unit: Unit) -> tuple[int, int]:
        """
        The PDF pages this unit's text covers, inclusive.

        A provision regularly runs across a page break, so "which page is
        Section 6(e) on" has no single answer. A citation pointing anywhere
        inside the span is pointing at the right provision.
        """
        first = page_for_offset(self.page_starts, unit.start)
        last = page_for_offset(self.page_starts, max(unit.start, unit.subtree_end - 1))
        return first, last

    def own_text(self, unit: Unit) -> str:
        return self.text[unit.start : unit.own_end].strip()

    def subtree_text(self, unit: Unit) -> str:
        return self.text[unit.start : unit.subtree_end].strip()

    @cached_property
    def by_citation(self) -> dict[str, Unit]:
        """
        Citation string to unit, for the deterministic lookup of task 5.7.

        First writer wins: a citation appearing twice means the outline has two
        nodes with the same number, and silently overwriting would make the
        lookup depend on traversal order.
        """
        out: dict[str, Unit] = {}
        for unit in self.units:
            out.setdefault(unit.citation, unit)
        return out

    def resolve(self, article: str, section: str) -> tuple[Unit | None, str]:
        """
        The unit for a citation, falling back to the nearest ancestor.

        The PDF's outline does not bookmark every subsection -- Art. VII 8(e),
        the sign-and-trade provision, has no entry at all. Returning nothing
        would leave the model with no text to quote for a rule the engine
        enforces, so the containing provision is returned instead, with the
        citation that was actually found. The caller can then say "Art. VII §8"
        rather than claiming to quote §8(e)(1).
        """
        wanted = f"Art. {article} §{section}"
        if exact := self.by_citation.get(wanted):
            return exact, wanted
        markers = _SUBSECTION.findall(section)
        head = section[: section.index("(")] if "(" in section else section
        for drop in range(1, len(markers) + 1):
            kept = markers[: len(markers) - drop]
            candidate = f"Art. {article} §{head}" + "".join(f"({m})" for m in kept)
            if found := self.by_citation.get(candidate):
                return found, candidate
        return None, wanted

    def articles(self) -> list[Unit]:
        return [u for u in self.units if u.article and not u.section]

    def sections(self) -> list[Unit]:
        return [u for u in self.units if u.section and not u.subsection]


TocEntry = tuple[int, str, int]


def _read_pdf(path: Path) -> tuple[str, list[int], list[TocEntry]]:
    """
    The only place that touches PyMuPDF.

    Confined to one function because PyMuPDF ships no type information, so
    every call into it needs an escape hatch. Keeping them here means the rest
    of the module stays checkable instead of the whole file being exempted.

    Returns the normalised document text, each page's start offset within it,
    and the bookmark outline.
    """
    doc = pymupdf.open(path)  # type: ignore[no-untyped-call]
    try:
        parts: list[str] = []
        starts: list[int] = []
        cursor = 0
        for number in range(doc.page_count):
            raw: str = doc[number].get_text()  # type: ignore[no-untyped-call]
            body = normalise(raw) + " "
            starts.append(cursor)
            parts.append(body)
            cursor += len(body)
        toc: list[TocEntry] = list(doc.get_toc())
    finally:
        doc.close()  # type: ignore[no-untyped-call]
    return "".join(parts), starts, toc


_ROMAN_VALUES = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}


def _roman(marker: str) -> int | None:
    lowered = marker.lower()
    if not lowered or any(ch not in _ROMAN_VALUES for ch in lowered):
        return None
    total = 0
    for i, ch in enumerate(lowered):
        value = _ROMAN_VALUES[ch]
        nxt = _ROMAN_VALUES.get(lowered[i + 1]) if i + 1 < len(lowered) else None
        total += -value if nxt and nxt > value else value
    return total


def _is_successor(prev: str, nxt: str) -> bool:
    """
    Whether `nxt` continues the series `prev` started.

    This is what separates a sibling from a child, and it works because the
    *first* marker of any series -- (a), (1), (i), (A) -- is never the successor
    of anything, so it always reads as a child. That dissolves the usual
    lowercase-letter versus lowercase-roman ambiguity without having to decide
    which a marker is: after (d), the marker (i) is not the letter that follows
    (e), so it opens a new depth; after (h) it is, so it continues the letters.

    An outline that skips a sibling would file it one level too deep. Measured
    against the engine's citation table, that does not happen here.
    """
    if prev.isdigit() and nxt.isdigit():
        return int(nxt) == int(prev) + 1
    if prev.isalpha() and nxt.isalpha() and prev.isupper() == nxt.isupper():
        if len(prev) == len(nxt) and len(set(prev)) == 1 and len(set(nxt)) == 1:
            # (a)..(z) then (aa), (bb), (cc) -- the doubled form appears at 1(cc).
            return ord(nxt[0]) == ord(prev[0]) + 1
        left, right = _roman(prev), _roman(nxt)
        if left is not None and right is not None and right == left + 1:
            return True
    return False


def _series(marker: str) -> str:
    """
    Which numbering series a marker belongs to: (a), (1) or (A).

    Only used to compare one marker against another, so the classic ambiguity
    between a lowercase letter and a lowercase roman numeral does not arise --
    both land in "lower", and the comparison asks whether two markers are the
    same *kind*, not which depth either sits at.
    """
    if marker.isdigit():
        return "digit"
    return "upper" if marker.isupper() else "lower"


@dataclass(frozen=True, slots=True)
class _Frame:
    """One level of the numbering context while walking the outline."""

    level: int
    article: str | None
    section: str | None
    full: tuple[str, ...]
    """The path including every marker this entry's title carried."""
    sibling_base: tuple[str, ...]
    """The path a same-series sibling of the trailing marker would take."""


def _numbering(level: int, title: str, stack: list[_Frame]) -> _Frame:
    """
    Place one outline entry in the citation numbering.

    The hard case is a title carrying more than one marker, like "(2) (i) At
    any point during a Salary Cap Year...". That single entry is both 2(e)(2)
    and its first child (i), and the outline then puts (A), (B), (ii) and (iii)
    all one level below it -- although (A) is a child of (i) while (ii) is a
    *sibling* of it. Outline depth alone cannot tell those apart.

    The series does. A marker of the same kind as the parent's trailing marker
    continues that series, so it is a sibling; a marker of a different kind
    opens a new depth, so it is a child.
    """
    parent = None
    for frame in stack:
        if frame.level >= level:
            break
        parent = frame

    article = parent.article if parent else None
    section = parent.section if parent else None
    inherited = parent.full if parent else ()

    if match := _ARTICLE.match(title):
        return _Frame(level, match.group(1).upper(), None, (), ())
    if match := _SECTION.match(title):
        return _Frame(level, article, match.group(1), (), ())

    leading = _LEADING_MARKERS.match(title)
    if not leading:
        return _Frame(level, article, section, inherited, parent.sibling_base if parent else ())

    markers = tuple(_SUBSECTION.findall(leading.group(1)))
    base = inherited
    if parent and markers and inherited and _is_successor(inherited[-1], markers[0]):
        # Continues the series the parent's trailing marker started, so it is a
        # sibling of it rather than a child. Covers both the compound-title case
        # and the outline's habit of nesting (d) under (c).
        base = inherited[:-1]

    full = (*base, *markers)
    return _Frame(level, article, section, full, (*base, markers[0]) if markers else base)


def load(pdf_path: Path | None = None) -> Outline:
    """
    Read the PDF and place every outline entry in the document text.

    Entries that cannot be located are collected on `Outline.unmatched` rather
    than skipped, because a silently missing unit is a hole in retrieval that
    nothing else would reveal.
    """
    text, page_starts, toc = _read_pdf(pdf_path or DEFAULT_PDF)

    located: list[tuple[int, int, int, str]] = []  # offset, level, page, title
    unmatched: list[tuple[int, str, int]] = []
    lowered = text.lower()

    for level, title, page in toc:
        if not 1 <= page <= len(page_starts):
            unmatched.append((level, title, page))
            continue
        needle = normalise(title).lower()[:PREFIX_CHARS]
        # Search from this entry's own page: the Table of Contents repeats
        # every heading verbatim and would otherwise match first.
        found = lowered.find(needle, page_starts[page - 1])
        if found < 0:
            unmatched.append((level, title, page))
            continue
        located.append((found, level, page, title))

    located.sort()
    offsets = [item[0] for item in located]

    units: list[Unit] = []
    stack: list[_Frame] = []
    for i, (start, level, page, title) in enumerate(located):
        own_end = offsets[i + 1] if i + 1 < len(offsets) else len(text)
        subtree_end = len(text)
        for j in range(i + 1, len(located)):
            if located[j][1] <= level:
                subtree_end = offsets[j]
                break
        frame = _numbering(level, title, stack)
        stack = [entry for entry in stack if entry.level < level]
        stack.append(frame)
        article, section, subsection = frame.article, frame.section, frame.full
        units.append(
            Unit(
                index=i,
                level=level,
                title=normalise(title),
                pdf_page=page,
                start=start,
                own_end=own_end,
                subtree_end=subtree_end,
                article=article,
                section=section,
                subsection=subsection,
            )
        )
    return Outline(text=text, units=units, page_starts=page_starts, unmatched=unmatched)


def page_for_offset(page_starts: list[int], offset: int) -> int:
    """Which PDF page an offset falls on."""
    return bisect_right(page_starts, offset)
