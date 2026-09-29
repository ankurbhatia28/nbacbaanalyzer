"""Citations are the join to retrieval, so they must be well-formed."""

from engine.citations import ALL_CITATIONS, TRANSACTION_RESTRICTIONS_TABLE, Citation


def test_every_citation_is_complete():
    for c in ALL_CITATIONS:
        assert c.article and c.section and c.title, c
        assert 1 <= c.page <= 676, c  # the document is 676 pages


def test_citations_render_for_display_and_for_retrieval():
    c = TRANSACTION_RESTRICTIONS_TABLE
    assert str(c) == "Article VII, Section 2(e)(4) (p. 214)"
    assert c.short == "Art. VII §2(e)(4)"


def test_citations_are_immutable():
    import dataclasses

    import pytest

    with pytest.raises(dataclasses.FrozenInstanceError):
        TRANSACTION_RESTRICTIONS_TABLE.page = 1  # type: ignore[misc]


def test_no_duplicate_article_section_pairs():
    seen: dict[tuple[str, str], Citation] = {}
    for c in ALL_CITATIONS:
        key = (c.article, c.section)
        assert key not in seen or seen[key] == c, f"conflicting citations for {key}"
        seen[key] = c
