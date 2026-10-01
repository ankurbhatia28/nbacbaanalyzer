"""
Retrieval units (task 5.3).

The property that matters most is that splitting loses nothing. A chunker that
drops a subsection produces a system that confidently cannot answer a question,
with no error anywhere to show why — the same invisible failure mode as letting
the model do arithmetic.
"""

import re

import pytest

from rag.chunks import MAX_CHARS, build
from rag.outline import DEFAULT_PDF, load

pytestmark = pytest.mark.skipif(not DEFAULT_PDF.exists(), reason="CBA PDF not present")


@pytest.fixture(scope="module")
def outline():
    return load()


@pytest.fixture(scope="module")
def chunks(outline):
    return build(outline)


def squash(text: str) -> str:
    """Compare text ignoring whitespace, since each chunk is stripped."""
    return re.sub(r"\s+", "", text)


def test_splitting_a_section_loses_none_of_its_text(outline, chunks):
    """
    The invariant. Checked on the Sections that actually get split, since an
    unsplit Section is trivially lossless.
    """
    for citation in ("Art. VII §6", "Art. VII §2", "Art. VII §4", "Art. XI §5"):
        section = outline.by_citation[citation]
        expected = squash(outline.subtree_text(section))
        got = squash(
            "".join(
                c.text
                for c in chunks
                if c.citation.startswith(citation + "(") or c.citation == citation
            )
        )
        assert got == expected, f"{citation} lost or duplicated text when split"


def test_every_chunk_is_under_the_ceiling_or_says_why(chunks):
    for chunk in chunks:
        assert chunk.char_count <= MAX_CHARS or chunk.oversized


def test_only_the_genuinely_unsplittable_units_are_oversized(chunks):
    """
    At the measured ceiling of 6,000 exactly one unit has no subsections to
    open: Art. XLII §3 is "Exhibits", whose contents the PDF bookmarks as
    top-level entries rather than as children of the Section, so the hierarchy
    offers nothing to split on.
    """
    oversized = {c.citation for c in chunks if c.oversized}
    assert oversized == {"Art. XLII §3"}


def test_a_chunk_carries_a_citation_that_resolves_back(outline, chunks):
    """A passage that cannot be cited is a passage the model must not quote."""
    for chunk in chunks[:200]:
        assert chunk.citation
        assert chunk.citation.startswith("Art. ")


def test_the_heading_path_puts_ancestor_wording_in_the_unit(chunks):
    """
    A subsection never repeats the heading it sits under, although that is how
    someone would search for it. "Exceptions to the Salary Cap" has to reach
    the chunk somehow.
    """
    tpe = next(c for c in chunks if c.citation == "Art. VII §6(j)(1)")
    assert "Exceptions to the Salary Cap" in tpe.heading_path
    assert "Article VII" in tpe.heading_path
    assert "Exceptions to the Salary Cap" not in tpe.text
    assert "Exceptions to the Salary Cap" in tpe.indexed_text


def test_a_parent_preamble_is_kept_when_its_children_are_split_out(outline, chunks):
    """
    The preamble carries the condition the subsections operate under -- 6(j)
    opens "Subject to the rules set forth in Section 2(e) above". Dropping it
    would strip the apron precondition off every exception beneath it.
    """
    preamble = next(c for c in chunks if c.citation == "Art. VII §6(j)")
    assert "Traded Player Exception" in preamble.text
    assert preamble.char_count < 4_000


def test_the_standard_tpe_is_retrievable_as_one_passage(chunks):
    """The provision Phase 3 leans on hardest."""
    hits = [
        c
        for c in chunks
        if "Standard Traded Player Exception" in c.text
        and "replace one (1) Traded Player" in c.text
    ]
    assert len(hits) == 1
    assert hits[0].citation == "Art. VII §6(j)(1)"
    assert hits[0].pdf_page == 264


def test_chunks_record_both_page_numberings(chunks):
    for chunk in chunks[:50]:
        assert chunk.pdf_page - chunk.printed_page == 24
        assert chunk.last_pdf_page >= chunk.pdf_page


def test_a_smaller_ceiling_produces_more_and_smaller_units(outline):
    """
    The ceiling is a parameter to be settled by the 5.8 eval, not a constant to
    be trusted, so it has to actually drive the split.
    """
    coarse = build(outline, max_chars=8_000)
    fine = build(outline, max_chars=1_000)
    assert len(fine) > len(coarse)
    # Anything above the ceiling must be a unit with nothing left to split on,
    # and must say so. A long preamble is such a unit, which this caught.
    for chunk in fine:
        assert chunk.char_count <= 1_000 or chunk.oversized


def test_no_article_is_emitted_as_a_whole_unit(chunks):
    """
    Emitting Articles as well as Sections would index the same text twice at
    two granularities and let one Article crowd out everything else.
    """
    assert not any(re.fullmatch(r"Art\. [IVXLC]+", c.citation) for c in chunks)
