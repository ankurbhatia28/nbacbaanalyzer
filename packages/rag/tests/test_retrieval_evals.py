"""
Retrieval evals (task 5.8).

Two jobs. The harness has to be trustworthy -- every expectation must be
reachable, or a low score measures the test rather than the system. And once it
is, it becomes the regression floor: retrieval must not quietly get worse.
"""

import pytest

from rag import index as ix
from rag.chunks import MAX_CHARS
from rag.chunks import build as build_chunks
from rag.crossrefs import build as build_graph
from rag.definitions import build as build_definitions
from rag.evals import (
    CUTOFFS,
    RULES,
    Kind,
    Question,
    all_questions,
    definition_questions,
    missing_terms,
    score,
)
from rag.outline import DEFAULT_PDF, load

pytestmark = pytest.mark.skipif(not DEFAULT_PDF.exists(), reason="CBA PDF not present")


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    outline = load()
    path = tmp_path_factory.mktemp("evals") / "eval.db"
    ix.build(
        path,
        build_chunks(outline),
        build_definitions(outline),
        build_graph(outline),
        outline,
    )
    return ix.open_index(path)


@pytest.fixture(scope="module")
def report(conn):
    return score(conn, all_questions(conn))


# -- the harness has to be trustworthy first ------------------------------


def test_the_golden_set_is_the_size_it_claims(conn):
    assert len(all_questions(conn)) == 50
    assert len(RULES) == 25


def test_every_expectation_is_reachable(report):
    """
    An expected citation that is not in the index measures the harness, not
    retrieval, so none may be left unmapped. §8(e)(1) is the case that forced
    this: the PDF never bookmarks it, so the question targets §8 instead.
    """
    assert report.unmapped == []


def test_every_definition_term_is_explainable(conn):
    """
    A term the index cannot explain means the definitions parser regressed.
    "Tax Level" was in this list and is quoted exactly once in the document
    without ever being defined -- my error, caught here.
    """
    assert missing_terms(conn) == []


def test_expectations_come_from_a_verified_source():
    """
    Not chosen freely. Every rules expectation traces to the engine's citation
    table, which task 5.2a checked provision by provision.
    """
    for question in RULES:
        assert question.source.startswith("engine.citations.")


def test_definition_expectations_are_read_from_the_index(conn):
    """So they cannot drift from what the parser actually extracted."""
    for question in definition_questions(conn):
        assert question.source.startswith("definitions index:")
        assert question.kind is Kind.TERM


def test_the_two_phrasings_are_balanced(report):
    """
    The split is the finding, so neither half may dominate the aggregate by
    being larger.
    """
    paraphrase = report.subset(Kind.PARAPHRASE).scored
    term = report.subset(Kind.TERM).scored
    assert abs(paraphrase - term) <= 2


# -- scoring -------------------------------------------------------------


def test_scoring_credits_the_chunk_that_contains_the_provision(conn):
    """
    A question about §6(j)(1)(i) is answered by the chunk for §6(j)(1), which
    contains it -- chunks stop splitting once a passage fits. Demanding an
    exact citation match would mark right answers wrong and make the score an
    artefact of the ceiling.
    """
    target = ix.containing_chunk(conn, "Art. VII §6(j)(1)(i)")
    assert target is not None
    assert target[0] != "Art. VII §6(j)(1)(i)"
    probe = Question("Standard Traded Player Exception", "Art. VII §6(j)(1)(i)", "probe")
    result = score(conn, [probe]).results[0]
    assert result.found


def test_a_question_that_cannot_be_answered_scores_as_a_miss(conn):
    probe = Question("zzzqqq nonsense", "Art. VII §6(j)(1)(i)", "probe")
    result = score(conn, [probe]).results[0]
    assert result.rank is None
    assert not result.found
    assert not result.exact_at_one


def test_recall_is_monotonic_in_k(report):
    values = [report.recall_at(k) for k in CUTOFFS]
    assert values == sorted(values)
    assert all(0.0 <= v <= 1.0 for v in values)


def test_mrr_is_bounded_and_consistent_with_recall_at_one(report):
    assert 0.0 <= report.mrr <= 1.0
    assert report.mrr >= report.recall_at(1) / max(CUTOFFS)


def test_depth_bounds_the_rank(conn):
    report = score(conn, all_questions(conn), depth=3)
    assert all(r.rank <= 3 for r in report.results if r.rank)


# -- the finding, and the floor ------------------------------------------


def test_a_query_carrying_the_term_of_art_does_better_than_a_paraphrase(report):
    """
    The result 5.8 exists to establish. BM25 is lexical, so it works when the
    question contains the provision's distinctive words and collapses when it
    does not -- "how much salary can a team take back" shares nothing with
    "replace one (1) Traded Player". The bottleneck is vocabulary, not ranking.
    """
    term = report.subset(Kind.TERM)
    paraphrase = report.subset(Kind.PARAPHRASE)
    assert term.recall_at(3) > paraphrase.recall_at(3) * 2
    assert term.mrr > paraphrase.mrr


def test_retrieval_does_not_regress_below_the_measured_floor(report):
    """
    A floor, not a pin. The figures move when chunking or the question set
    changes, and pinning them would turn every improvement into a failing test.
    Set well under what is measured today (recall@10 62%, MRR 0.280) so this
    catches a real regression rather than noise.
    """
    assert report.recall_at(10) >= 0.50, f"recall@10 fell to {report.recall_at(10):.1%}"
    assert report.mrr >= 0.20, f"MRR fell to {report.mrr:.3f}"


def test_the_chosen_ceiling_is_the_one_that_was_measured():
    """
    6,000 was best or tied-best on every metric in the sweep. If this changes,
    the sweep should be rerun rather than the constant edited.
    """
    assert MAX_CHARS == 6_000


def test_the_report_shows_the_split_not_just_an_aggregate(report):
    """A single number averages two different situations."""
    rendered = report.render()
    assert "by how the question is phrased" in rendered
    assert Kind.PARAPHRASE.value in rendered
    assert Kind.TERM.value in rendered
