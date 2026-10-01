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
    score_named_lookup,
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

    Set under what is measured today (recall@1 34%, recall@10 66%, MRR 0.433)
    but **above** what BM25 scored without coverage re-ranking (16% / 62% /
    0.280), so removing the re-ranker fails here rather than passing quietly.
    """
    assert report.recall_at(1) >= 0.25, f"recall@1 fell to {report.recall_at(1):.1%}"
    assert report.recall_at(10) >= 0.55, f"recall@10 fell to {report.recall_at(10):.1%}"
    assert report.mrr >= 0.35, f"MRR fell to {report.mrr:.3f}"


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


# -- the ranker, and the failures that motivated it -----------------------


@pytest.mark.parametrize(
    ("query", "must_not_win"),
    [
        ("Is there a larger allowance for matching salary in a trade?", "Art. III §2"),
        ("Can a team put two contracts together to bring back one bigger salary?", "Art. II §9"),
    ],
)
def test_a_single_rare_word_no_longer_picks_the_result(conn, query, must_not_win):
    """
    The concrete failures that forced the re-ranker. Ranking on BM25 alone,
    "allowance" pulled up **Meal Expense Allowance** (Art. III §2) and
    "contracts" pulled up **10-Day Contracts** (Art. II §9) -- each time one
    rare-ish word chose the chunk.
    """
    top = ix.search(conn, query, limit=3)
    assert all(hit.citation != must_not_win for hit in top), (
        f"{must_not_win} came back for {query!r}"
    )


def test_the_remaining_gap_is_vocabulary_and_is_not_fixable_by_ranking(conn):
    """
    Kept as evidence, not as a passing bar. "Is there a cap on how many
    contracts can be combined at once?" cannot be answered lexically: the
    provision (§6(j)(4)) says *aggregating*, never *combined*, so the query's
    key concept word appears nowhere in the target. Coverage re-ranking cannot
    help -- the target scores 2 of 5 terms and so do several unrelated
    passages, leaving the order to a BM25 tiebreak.

    This is the shape of what is left after the re-ranker, and the reason the
    answer is query expansion or dense retrieval rather than more ranking work.
    """
    query = "Is there a cap on how many contracts can be combined at once?"
    target = ix.containing_chunk(conn, "Art. VII §6(j)(4)(ii)")
    assert target is not None
    passage = ix.fetch(conn, target[0], target[1])
    assert passage is not None
    assert "aggregat" in passage.body.lower()
    assert "combined" not in passage.body.lower()
    assert target not in [(h.citation, h.ordinal) for h in ix.search(conn, query, limit=10)]


def test_results_are_ordered_by_coverage_then_bm25(conn):
    """
    Breadth of match first, score second. The reverse order is what produced
    the failures above.
    """
    hits = ix.search(conn, "aggregated traded player exception salary", limit=8)
    keys = [(-hit.coverage, hit.score) for hit in hits]
    assert keys == sorted(keys)


def test_coverage_counts_distinct_query_terms(conn):
    hits = ix.search(conn, "Standard Traded Player Exception", limit=3)
    assert hits[0].coverage >= 3
    assert all(hit.coverage <= 4 for hit in hits), "cannot exceed the number of query terms"


def test_a_wider_pool_does_not_change_the_leader_for_a_term_of_art(conn):
    """The pool size is a recall/precision dial, not a correctness dependency."""
    narrow = ix.search(conn, "Expanded Traded Player Exception", limit=1, pool=10)
    wide = ix.search(conn, "Expanded Traded Player Exception", limit=1, pool=200)
    assert narrow[0].citation == wide[0].citation


def test_stop_words_are_dropped_but_a_stop_word_only_query_still_runs(conn):
    from rag.index import query_terms

    assert query_terms("How much can it be?") == []
    ix.search(conn, "How much can it be?", limit=3)
    assert "salary" in query_terms("How much salary can a team take back?")


# -- D14 option A: resolve to a name, then look it up ---------------------


def test_the_vocabulary_is_the_documents_own(conn):
    """
    612 names: 454 headings the drafters wrote plus the defined terms. The
    closed set intent extraction picks from, so the model chooses the
    document's words rather than inventing a term that is then searched for.

    Was 670 before the title-case filter. The heading pattern matched any
    capitalised run ending in a period or colon, which caught sentences as well
    as titles -- "Notwithstanding Section 2(a) above, except as provided" and
    "Beginning at 12" were both in the list. 60 such entries were removed, and
    the next test holds that removing them cost no provision.
    """
    names = ix.vocabulary_names(conn)
    assert len(names) == 612
    assert len(ix.vocabulary_names(conn, "heading")) == 454
    assert names == sorted(names)
    assert all(name == name.lower() for name in names), "stored normalised"


@pytest.mark.parametrize(
    ("name", "citation"),
    [
        ("Standard Traded Player Exception", "Art. VII §6(j)(1)(i)"),
        ("expanded traded player exception", "Art. VII §6(j)(1)(iv)"),
        ("Transaction Restrictions Table", "Art. VII §2(e)(4)"),
        ("Over 38 Rule", "Art. VII §3(a)(2)"),
        ("Apron Team Salary", "Art. VII §2(e)(1)"),
        ("Trade Rules", "Art. VII §8"),
    ],
)
def test_a_name_resolves_to_its_provision(conn, name, citation):
    """
    Exactly, and case-insensitively. "Transaction Restrictions Table" and
    "Over 38 Rule" end their headings with a colon rather than a period, and
    were missed until the heading pattern allowed for it.
    """
    resolved = ix.resolve_term(conn, name)
    assert resolved is not None
    assert resolved[0] == citation


def test_an_unknown_name_resolves_to_nothing_rather_than_a_near_miss(conn):
    """
    Fuzzy matching here would resolve "traded player" to the Standard Traded
    Player Exception or to the definition of a Traded Player depending on edit
    distance, and quietly citing the wrong provision is the failure this
    project is arranged against. The caller falls back to search instead.
    """
    assert ix.resolve_term(conn, "the thing about trades") is None
    assert ix.resolve_term(conn, "") is None


def test_every_provision_the_engine_cites_is_nameable(conn):
    """
    Eleven of the 25 have no heading of their own -- §6(j)(4)(i) opens "No Team
    may aggregate" and was never given a title -- but the provision containing
    them does, which is enough to reach the right region.
    """
    report = score_named_lookup(conn)
    assert report.unnameable == 0
    assert report.exact == 14
    assert report.via_ancestor == 11


def test_filtering_sentences_out_of_the_vocabulary_cost_no_provision(conn):
    """
    The title-case filter removed 60 entries. If it had removed one that was
    the only route to a provision, reach would have dropped below 100% -- which
    is what the next test would catch, so this states the intent directly.
    """
    names = set(ix.vocabulary_names(conn))
    assert "notwithstanding any other provision of this agreement" not in names
    assert "trade rules" in names
    assert "standard traded player exception" in names
    assert score_named_lookup(conn).unnameable == 0


def test_naming_a_provision_reaches_its_text_every_time(conn):
    """
    The measurement that settled D14. Searching with a paraphrase reaches the
    right provision 20% of the time at recall@3; naming it and looking it up
    reaches it 100% of the time.
    """
    report = score_named_lookup(conn)
    assert report.reach == 1.0, f"missed: {report.misses}"


def test_a_section_level_name_returns_enough_breadth_to_find_an_unnamed_rule(conn):
    """
    §8(g), the rookie-extension trade rule, has no name; the nearest one is
    "trade rules" for the whole of §8. At 5 subsections it was missed, which is
    why a Section-level citation returns more.
    """
    from rag.retrieve import for_citation

    resolved = ix.resolve_term(conn, "trade rules")
    assert resolved is not None
    result = for_citation(conn, resolved[0])
    labels = [p.label for p in result.passages]
    assert "Art. VII §8(g)" in labels


def test_breadth_is_not_spent_on_a_lookup_that_already_names_a_subsection(conn):
    """The extra text is for the Section case only."""
    from rag.retrieve import for_citation

    result = for_citation(conn, "Art. VII §6(j)(1)")
    assert len(result.passages) == 1
