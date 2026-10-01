"""
The definitions index (task 5.4).

Article I opens "As used in this Agreement, the following terms shall have the
following meanings", and the terms it fixes govern every other Article. A
passage that turns on what "Salary" or "Apron Team Salary" means is not
self-contained: read without the definition it supports a confident wrong
answer, which is worse than no answer.

So defined terms are extracted from the document and attached to the passages
that use them. Two things make that worth doing carefully:

**Definitions are not only in the Definitions sections.** Art. I §1 holds 87,
but Art. VII §1 adds its own, Art. XXXIII another set, and some sit alone in
the Article that needs them -- "Force Majeure Event" is defined at Art. XXXIX
§5(a). Scanning only the sections titled "Definitions" would miss those, so
every unit is scanned.

**Matching has to be case-sensitive.** The convention is that a defined term is
Capitalised wherever it carries its defined meaning, and lowercase where it
does not. "Player" and "player" are different words in this document, and a
case-insensitive match would attach the definition of the first to every
occurrence of the second.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cached_property

from .outline import Outline, Unit

_QUOTED = re.compile(r"“([^”]+)”")
_MARKER = r"^\((?:[A-Za-z0-9]+)\)\s*"

_DEFINITION = re.compile(
    _MARKER
    # An optional "The term" lead-in, as at Art. I §1(nn).
    + r"(?:The term\s+)?"
    # One or more quoted terms. Separators seen in the document: "or", "and",
    # a comma inside the closing quote, and a parenthetical alias such as
    # ("Early Termination Option" (or "ETO")).
    + r"((?:“[^”]+”[,;]?\s*(?:\(\s*(?:or|also)\s*“[^”]+”\s*\))?"
    + r"\s*(?:or|and)?\s*)+)"
    + r"(?:means|shall mean|refers to|shall refer to|has the meaning)",
    re.I,
)
"""A definition: the quoted term or terms, then the defining verb."""

_SEE_ALSO = re.compile(
    _MARKER + r"((?:“[^”]+”[,;]?\s*(?:or|and)?\s*)+)" + r"\(\s*see\s+“([^”]+)”\s*\)"
)
"""A pointer rather than a definition: `"Contract" (see "Uniform Player Contract")`."""


@dataclass(frozen=True, slots=True)
class Definition:
    """One defined term, with the provision that fixes its meaning."""

    term: str
    citation: str
    text: str
    pdf_page: int
    aliases: tuple[str, ...] = ()

    @property
    def names(self) -> tuple[str, ...]:
        return (self.term, *self.aliases)


@dataclass
class DefinitionIndex:
    definitions: list[Definition] = field(default_factory=list)
    pointers: dict[str, str] = field(default_factory=dict)
    """Terms that redirect: "Player Contract" -> "Uniform Player Contract"."""

    @cached_property
    def by_name(self) -> dict[str, Definition]:
        """
        Every name a definition answers to, including aliases and pointers.

        Aliases are registered with `setdefault` so a real definition is never
        displaced by another term's alias.
        """
        out: dict[str, Definition] = {}
        for definition in self.definitions:
            out[definition.term] = definition
        for definition in self.definitions:
            for alias in definition.aliases:
                out.setdefault(alias, definition)
        for name, target in self.pointers.items():
            if target in out:
                out.setdefault(name, out[target])
        return out

    @cached_property
    def _matcher(self) -> re.Pattern[str]:
        """
        One alternation over every name, longest first.

        Longest-first matters: "Apron Team Salary" must win over "Salary",
        or the specific term is reported as the generic one. Case-sensitive by
        design -- see the module docstring.
        """
        names = sorted(self.by_name, key=len, reverse=True)
        joined = "|".join(re.escape(name) for name in names)
        return re.compile(rf"\b({joined})\b")

    def terms_in(self, text: str) -> list[str]:
        """
        Which defined terms a passage uses, in order of appearance.

        Ranking belongs to `relevant_to`, which sorts by specificity; a scanner
        reporting document order is the more useful primitive.

        Overlaps are resolved by position: the "Team Salary" inside a match on
        "Apron Team Salary" is not reported again. A separate, later occurrence
        of "Team Salary" still is -- it is a real use of the term.
        """
        seen: list[str] = []
        taken: list[tuple[int, int]] = []
        for match in self._matcher.finditer(text):
            start, end = match.span(1)
            if any(a <= start and end <= b for a, b in taken):
                continue
            taken.append((start, end))
            name = match.group(1)
            if name not in seen:
                seen.append(name)
        return seen

    def relevant_to(self, text: str, limit: int = 6) -> list[Definition]:
        """
        The definitions worth attaching to a passage.

        Ubiquitous terms are dropped rather than ranked down. "Player" and
        "Team" are defined, appear in almost every provision, and attaching
        their definitions tells a reader nothing while crowding out the term
        the passage actually turns on. Specificity is approximated by length,
        which tracks it well here: the long names are the terms of art.
        """
        matched = [
            (name, self.by_name[name]) for name in self.terms_in(text) if name in self.by_name
        ]
        out: list[Definition] = []
        # Suppression is checked against the name that matched *and* the term it
        # resolves to: "Team" is a pointer to "Member", so filtering only on the
        # canonical term would let every provision mentioning a team pull in the
        # definition of a franchise.
        for name, definition in sorted(matched, key=lambda pair: -len(pair[0])):
            if name in UBIQUITOUS or definition.term in UBIQUITOUS:
                continue
            if definition not in out:
                out.append(definition)
            if len(out) == limit:
                break
        return out


UBIQUITOUS = frozenset(
    {
        "Agreement",
        "Member",
        "Team",
        "NBA Team",
        "Season",
        "Regular Season",
        "Contract",
        "Player Contract",
        "Uniform Player Contract",
        "Salary Cap Year",
    }
)
"""
Defined terms too common to be informative as attachments.

Every entry must be a name the document actually defines -- a test enforces
that. An earlier version listed "Player" and "NBA", neither of which the CBA
defines at all (it defines "Traded Player", "Veteran Player" and so on), so the
list was claiming to suppress terms it had never seen.

Held as an explicit list rather than a frequency cutoff so it can be read and
argued with. A threshold would silently change what it hides as the document
changed.
"""


def _terms_from(blob: str) -> list[str]:
    return [term.strip().strip(",;") for term in _QUOTED.findall(blob)]


def build(outline: Outline) -> DefinitionIndex:
    """
    Scan every unit for a definition.

    A unit whose text opens with a quoted term and a defining verb *is* a
    definition, wherever it sits in the document.
    """
    index = DefinitionIndex()
    seen: set[str] = set()
    for unit in outline.units:
        if not unit.subsection:
            continue
        body = outline.own_text(unit)
        if not body:
            continue

        if pointer := _SEE_ALSO.match(body):
            target = pointer.group(2).strip()
            for name in _terms_from(pointer.group(1)):
                index.pointers[name] = target
            continue

        match = _DEFINITION.match(body)
        if not match:
            continue
        names = _terms_from(match.group(1))
        if not names or names[0] in seen:
            continue
        seen.add(names[0])
        index.definitions.append(
            Definition(
                term=names[0],
                citation=unit.citation,
                text=outline.subtree_text(unit),
                pdf_page=unit.pdf_page,
                aliases=tuple(names[1:]),
            )
        )
    return index


def definition_sections(outline: Outline) -> list[Unit]:
    """The Sections explicitly titled "Definitions", for reporting."""
    return [u for u in outline.sections() if "definition" in u.title.lower()]
