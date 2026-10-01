"""
Structure taken from the document (tasks 5.1, 5.2).

The outline is the spine of retrieval: if a unit is mis-numbered, every
citation built on it is wrong, and the failure is invisible — a confident quote
attached to the wrong provision. So these tests check the numbering against
things the document itself says, not against what the code produced.
"""

import pytest

import engine.citations as engine_citations
from engine.citations import Citation
from rag.outline import DEFAULT_PDF, PRINTED_PAGE_OFFSET, _is_successor, load, normalise

pytestmark = pytest.mark.skipif(not DEFAULT_PDF.exists(), reason="CBA PDF not present")


@pytest.fixture(scope="module")
def outline():
    return load()


ENGINE_CITATIONS = [
    (name, value) for name, value in vars(engine_citations).items() if isinstance(value, Citation)
]


def test_the_outline_is_read_whole(outline):
    """
    2,412 bookmark entries; one is unmatchable because its own title is
    malformed (words run together with no spaces), which no search can locate.
    Anything beyond that is a hole in retrieval.
    """
    assert len(outline.units) == 2411
    assert len(outline.unmatched) == 1
    assert "EXHIBIT A" in outline.unmatched[0][1]


def test_the_document_has_the_articles_it_says_it_has(outline):
    assert len(outline.articles()) == 42
    numbers = [u.article for u in outline.articles()]
    assert numbers[:3] == ["I", "II", "III"]
    assert len(set(numbers)) == 42, "no Article number appears twice"


@pytest.mark.parametrize(
    ("citation", "expected_page", "opening"),
    [
        ("Art. VII §6(j)(1)(i)", 264, "Standard Traded Player Exception"),
        ("Art. VII §2(e)(2)(i)(A)", 211, "A Team may not engage in a transaction"),
        ("Art. XXIV §2(a)", 438, None),
        ("Art. I §1", 25, None),
    ],
)
def test_known_provisions_land_where_they_should(outline, citation, expected_page, opening):
    """Spot checks against provisions read by hand during Phase 3."""
    unit = outline.by_citation[citation]
    assert unit.pdf_page == expected_page
    if opening:
        assert opening in outline.subtree_text(unit)[:200]


def test_the_printed_folio_is_offset_from_the_pdf_page(outline):
    """
    The pages are numbered 24 behind the PDF, so "p. 211" means different things
    depending on which you meant. Both are kept so a citation can say which.
    """
    unit = outline.by_citation["Art. I §1"]
    assert unit.pdf_page == 25
    assert unit.printed_page == 1
    assert unit.pdf_page - unit.printed_page == PRINTED_PAGE_OFFSET


# -- the numbering ---------------------------------------------------------


def test_a_compound_title_is_split_into_its_levels(outline):
    """
    The entry for 2(e)(2)(i) is titled "(2) (i) At any point during a Salary Cap
    Year...", carrying two levels in one bookmark. Taking only the first marker
    would file it as 2(e)(2) and collide with its own parent.
    """
    unit = outline.by_citation["Art. VII §2(e)(2)(i)"]
    assert unit.subsection == ("e", "2", "i")
    assert unit.title.startswith("(2) (i)")


def test_a_child_of_a_compound_entry_nests_under_both_markers(outline):
    """(A) sits beneath (i), so it is 2(e)(2)(i)(A) and not 2(e)(2)(A)."""
    assert outline.by_citation["Art. VII §2(e)(2)(i)(A)"].subsection == ("e", "2", "i", "A")
    assert "Art. VII §2(e)(2)(A)" not in outline.by_citation


def test_a_sibling_of_a_compound_entry_does_not_nest_under_it(outline):
    """
    (ii) continues the series (i) started, so it belongs beside it. The outline
    puts them at the same depth, which on its own cannot distinguish the two.
    """
    unit = outline.by_citation["Art. VII §2(e)(2)(ii)"]
    assert unit.subsection == ("e", "2", "ii")
    assert unit.title.startswith("(ii)")


def test_a_bare_marker_entry_is_placed_beside_its_predecessor(outline):
    """
    The outline nests Section 8's (d) under (c). (d) follows (c) in the letters,
    so it is a sibling: 8(d), not 8(c)(d).
    """
    subsections = {
        u.subsection[0]
        for u in outline.units
        if u.article == "VII" and u.section == "8" and u.subsection
    }
    assert {"a", "b", "c", "d", "g"} <= subsections
    assert "Art. VII §8(c)(d)" not in outline.by_citation


@pytest.mark.parametrize(
    ("prev", "nxt", "sibling"),
    [
        ("c", "d", True),  # letters continue
        ("i", "ii", True),  # romans continue
        ("1", "2", True),
        ("bb", "cc", True),  # the doubled form, as at 1(cc)
        ("d", "i", False),  # (i) opens the romans beneath (d)
        ("j", "1", False),  # a different series is always a child
        ("1", "i", False),
        ("i", "A", False),
        ("a", "a", False),  # not its own sibling
    ],
)
def test_successor_separates_a_sibling_from_a_child(prev, nxt, sibling):
    """
    The rule the numbering rests on. The first marker of any series is never
    the successor of anything, which is what lets (i) read as a roman child
    after (d) and as the letter after (h) without deciding which it "is".
    """
    assert _is_successor(prev, nxt) is sibling


# -- the engine's citation table -------------------------------------------


def test_every_engine_citation_resolves_to_a_provision(outline):
    """
    The join between the rules engine and the document. A violation code points
    at a citation, and the citation has to reach text — otherwise the model is
    asked to quote something that was never found.
    """
    unresolved = [
        name for name, c in ENGINE_CITATIONS if outline.resolve(c.article, c.section)[0] is None
    ]
    assert unresolved == []


@pytest.mark.parametrize(
    ("name", "citation"), ENGINE_CITATIONS, ids=[n for n, _ in ENGINE_CITATIONS]
)
def test_each_engine_citation_points_inside_its_own_provision(outline, name, citation):
    """
    The cross-check that found four errors in the hand-maintained table: the
    apron levels cited to the Apron Team Salary computation rather than to
    §2(a)(4)(iii) where they are defined, the Non-Taxpayer MLE cited to a page
    already occupied by §6(f), and two off-by-one pages.

    Asserted as "inside the span" rather than "equal to the first page" because
    a provision regularly runs across a page break, and pointing at the
    sentence that matters is legitimate.
    """
    unit, _ = outline.resolve(citation.article, citation.section)
    first, last = outline.page_range(unit)
    assert first <= citation.page <= last, (
        f"{name} cites p.{citation.page}; §{citation.section} covers pp.{first}-{last}"
    )


def test_a_missing_subsection_falls_back_to_the_provision_that_contains_it(outline):
    """
    The PDF does not bookmark Art. VII §8(e), the sign-and-trade rule, at all.
    Returning nothing would leave a rule the engine enforces with no text to
    quote, so the containing Section is returned along with the citation that
    was actually reached — the caller must not claim to be quoting §8(e)(1).
    """
    assert "Art. VII §8(e)(1)" not in outline.by_citation
    unit, used = outline.resolve("VII", "8(e)(1)")
    assert unit is not None
    assert used == "Art. VII §8"
    assert "Trade Rules" in unit.title


def test_an_exact_hit_reports_itself_rather_than_an_ancestor(outline):
    unit, used = outline.resolve("VII", "6(j)(1)(i)")
    assert used == "Art. VII §6(j)(1)(i)"
    assert unit is outline.by_citation[used]


# -- text extraction -------------------------------------------------------


def test_a_unit_carries_its_own_text_and_its_subtree_separately(outline):
    """
    A Section's own text stops where its first subsection begins; the subtree
    includes them. Retrieval wants the second, a heading listing wants the first.
    """
    section = outline.by_citation["Art. VII §6(j)"]
    assert len(outline.subtree_text(section)) > len(outline.own_text(section))


def test_text_is_not_taken_from_the_table_of_contents(outline):
    """
    Every heading appears twice: once in the Table of Contents and once in the
    body. Searching from the entry's own page is what keeps the body copy.
    """
    unit = outline.by_citation["Art. VII §6(j)"]
    assert unit.pdf_page > 24
    body = outline.subtree_text(unit)
    assert "Traded Player Exception" in body
    assert len(body) > 500, "a Table of Contents line would be short"


def test_normalise_collapses_the_hard_wrapping():
    assert normalise("a\n  b \n\n c") == "a b c"
