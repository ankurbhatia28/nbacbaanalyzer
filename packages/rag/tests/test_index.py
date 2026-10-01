"""
BM25 retrieval over FTS5 (tasks 5.6, 5.7, 5.9).

The index is a build artifact (ADR-004): written once, opened read-only, and
self-contained so the serving application never re-parses a 676-page PDF.
"""

import sqlite3

import pytest

import engine.citations as engine_citations
from engine.citations import Citation
from rag import index as ix
from rag.chunks import build as build_chunks
from rag.crossrefs import build as build_graph
from rag.definitions import build as build_definitions
from rag.outline import DEFAULT_PDF, load
from rag.retrieve import Why, figures_in, for_citation, retrieve

pytestmark = pytest.mark.skipif(not DEFAULT_PDF.exists(), reason="CBA PDF not present")

ENGINE_CITATIONS = [
    (name, value) for name, value in vars(engine_citations).items() if isinstance(value, Citation)
]


@pytest.fixture(scope="module")
def artifact(tmp_path_factory):
    outline = load()
    path = tmp_path_factory.mktemp("rag") / "cba.db"
    ix.build(
        path,
        build_chunks(outline),
        build_definitions(outline),
        build_graph(outline),
        outline,
    )
    return path


@pytest.fixture(scope="module")
def conn(artifact):
    return ix.open_index(artifact)


# -- the artifact ----------------------------------------------------------


def test_the_index_holds_every_chunk(conn):
    assert ix.count(conn) == 1276


def test_the_artifact_is_self_contained(conn):
    """
    Definitions and cross-references are written in, so nothing at runtime
    needs the PDF. ADR-004 makes this file the whole of what ships.
    """
    assert ix.definition_for(conn, "Apron Team Salary") is not None
    assert ix.targets_of(conn, "Art. VII §6(j)(1)(i)") == ["Art. VII §2(e)"]
    assert len(ix.all_definition_names(conn)) == 176


def test_it_opens_read_only(artifact):
    """The serving application must not be able to write to it."""
    conn = ix.open_index(artifact)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM chunks")


# -- queries ---------------------------------------------------------------


@pytest.mark.parametrize(
    "query",
    [
        "what does 6(j) say",  # parentheses are FTS5 grouping operators
        'the "expanded" exception',  # quotes are phrase delimiters
        "apron AND NOT salary",  # bare boolean operators
        "second apron*",  # a prefix wildcard
        "trade^exception NEAR cap",
        "",  # nothing at all
        "the a an of and",  # only stop words
    ],
)
def test_a_query_with_operators_in_it_does_not_raise(conn, query):
    """
    The trap this guards. "what does 6(j) say" is not a query that returns
    nothing -- passed to MATCH unescaped it is a *syntax error*. Putting user
    text straight into a MATCH expression is the same mistake as building SQL
    by string concatenation.
    """
    ix.search(conn, query, limit=3)


def test_the_term_of_art_query_finds_its_provision(conn):
    """The case BM25 is chosen for (D12): the question contains the term."""
    hits = ix.search(conn, "Standard Traded Player Exception", limit=3)
    assert hits[0].citation == "Art. VII §6(j)(1)"


def test_lower_bm25_is_a_better_match(conn):
    hits = ix.search(conn, "traded player exception", limit=5)
    scores = [h.score for h in hits]
    assert scores == sorted(scores)
    assert hits[0].rank >= hits[-1].rank


def test_a_query_matching_nothing_returns_nothing(conn):
    assert ix.search(conn, "zzzzqqqx", limit=5) == []


def test_the_heading_path_is_searchable(conn):
    """
    A subsection never repeats the heading it sits under, so indexing the body
    alone would make it unfindable by the words a reader would actually use.
    """
    hits = ix.search(conn, "Exceptions to the Salary Cap aggregated", limit=5)
    assert any(h.citation.startswith("Art. VII §6(j)") for h in hits)


# -- passages that share a citation ---------------------------------------


def test_passages_sharing_a_citation_are_distinguishable(conn):
    """
    Art. VII §2(e) covers its heading and five worked Examples. Two results
    both labelled "Art. VII §2(e)" would be indistinguishable to a reader.
    """
    first = ix.fetch(conn, "Art. VII §2(e)", ordinal=1)
    later = ix.fetch(conn, "Art. VII §2(e)", ordinal=6)
    assert first is not None and later is not None
    assert first.label == "Art. VII §2(e)"
    assert later.label == "Art. VII §2(e) (passage 6)"
    assert first.body != later.body


# -- the deterministic citation path (5.7) --------------------------------


@pytest.mark.parametrize(
    ("name", "citation"), ENGINE_CITATIONS, ids=[n for n, _ in ENGINE_CITATIONS]
)
def test_every_engine_citation_reaches_substantive_text(conn, name, citation):
    """
    The join the whole design rests on: a violation code names a citation, and
    the citation has to produce text the model can quote.

    Asserted on total characters rather than "a passage came back", because a
    lookup that returns "Section 8. Trade Rules." -- 23 characters of heading --
    reports success and conveys nothing.
    """
    result = for_citation(conn, f"Art. {citation.article} §{citation.section}")
    assert result.passages, f"{name} resolved to no text at all"
    assert sum(len(p.text) for p in result.passages) > 200, f"{name} resolved to a bare heading"


def test_a_citation_finer_than_any_chunk_says_what_it_returned(conn):
    """
    §2(e)(2)(i)(A) is inside the chunk for §2(e)(2)(i). The caller must not
    claim to be quoting (A) while holding (i), so the substitution is reported.
    """
    result = for_citation(conn, "Art. VII §2(e)(2)(i)(A)")
    assert result.resolved_to == "Art. VII §2(e)(2)(i)"
    assert "may not engage in a transaction" in result.passages[0].text


def test_an_exact_citation_reports_no_substitution(conn):
    result = for_citation(conn, "Art. VII §6(j)(1)")
    assert result.resolved_to is None
    assert result.passages[0].why is Why.CITED


def test_a_section_citation_brings_its_subsections(conn):
    """
    "Art. VII §8" resolves to a 23-character heading on its own. The provision
    is in the subsections beneath it.
    """
    result = for_citation(conn, "Art. VII §8")
    labels = [p.label for p in result.passages]
    assert labels[0] == "Art. VII §8"
    assert "Art. VII §8(a)" in labels
    assert sum(len(p.text) for p in result.passages) > 1_000


def test_an_unknown_citation_returns_nothing_rather_than_a_near_miss(conn):
    """A plausible substitute is worse than nothing on the deterministic path."""
    assert for_citation(conn, "Art. ZZ §99(q)").passages == []


# -- retrieval, composed --------------------------------------------------


def test_retrieval_brings_in_what_a_match_depends_on(conn):
    """
    §6(j)(1)(i) opens "Subject to the rules set forth in Section 2(e) above".
    A reader given the exception without its precondition has been misled.
    """
    result = retrieve(conn, "Standard Traded Player Exception", limit=3)
    assert any(p.why is Why.REFERENCED for p in result.passages)
    assert all(p.referenced_by for p in result.passages if p.why is Why.REFERENCED)


def test_expansion_is_capped(conn):
    """
    The Transaction Restrictions Table cites eight provisions on its own.
    Without a cap, one broad match buries the passages that answered the query.
    """
    result = retrieve(conn, "apron restrictions trade exception salary", limit=5)
    expanded = [p for p in result.passages if p.why is Why.REFERENCED]
    assert len(expanded) <= 4


def test_context_is_not_counted_as_evidence(conn):
    """
    An answer resting only on expansion means the query never matched the
    provision it claims to rely on.
    """
    result = retrieve(conn, "Standard Traded Player Exception", limit=3)
    assert result.evidence
    assert all(p.why is Why.MATCHED for p in result.evidence)
    assert len(result.evidence) <= len(result.passages)


def test_expansion_can_be_turned_off(conn):
    result = retrieve(conn, "Standard Traded Player Exception", limit=3, expand=False)
    assert all(p.why is Why.MATCHED for p in result.passages)


def test_definitions_are_attached_to_what_was_retrieved(conn):
    result = retrieve(conn, "apron team salary computation", limit=3)
    assert result.definitions
    assert all(d.citation.startswith("Art. ") for d in result.definitions)


def test_ubiquitous_terms_are_not_attached(conn):
    result = retrieve(conn, "a Team and a Player under this Agreement", limit=3)
    assert not any(
        d.term in {"Member", "Agreement", "Uniform Player Contract"} for d in result.definitions
    )


# -- the numeric guardrail (5.9) ------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("the sum of $250,000", ["$250,000"]),
        ("one hundred twenty-five percent (125%)", ["125%"]),
        ("up to $7,500,000 or 200%", ["$7,500,000", "200%"]),
        ("a figure of 7,500,000", ["7,500,000"]),
        ("no numbers here", []),
    ],
)
def test_figures_are_detected_in_prose(text, expected):
    assert figures_in(text) == expected


def test_retrieved_prose_reports_its_figures(conn):
    """
    Marked so they can be refused, not used. Almost every number in this
    document belongs to a different exception, an example, or a prior CBA than
    the one asked about -- a figure reaching a user comes from a tool result.
    """
    result = retrieve(conn, "traded player exception two hundred percent", limit=3)
    assert result.figures
    assert "must not be answered from" in result.render()
