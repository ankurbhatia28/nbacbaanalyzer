"""
The query eval set (task 4.7) must hold itself to its own standards.

The set is data, so the tests here are about its integrity: no question
asserts nothing, no gap goes unexplained, and the grader accepts a correct
translation rather than demanding the reference query verbatim.
"""

from pathlib import Path

import pytest

from nbadata.db import open_readonly
from nbadata.evals.queries import GOLDEN, Category, Golden, grade, run_query_evals
from nbadata.ingest.load import load
from nbadata.query import Agg, Filter, Op, Order, Projection, Query

CSV_DIR = Path(__file__).resolve().parents[3] / "scraper" / "out"
needs_data = pytest.mark.skipif(
    not (CSV_DIR / "contracts.csv").exists(), reason="scraper output not present"
)


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    db = tmp_path_factory.mktemp("qe") / "evals.db"
    load(CSV_DIR, db)
    return open_readonly(db)


def test_every_question_is_unique_and_reachable():
    ids = [g.id for g in GOLDEN]
    assert len(ids) == len(set(ids)), "duplicate question id"
    assert all(g.question.endswith("?") for g in GOLDEN), "every golden is a question"


def test_a_reference_query_without_a_check_is_rejected():
    """A question that asserts nothing about its answer is not an eval."""
    with pytest.raises(ValueError, match="asserts nothing"):
        Golden(
            id="x",
            question="How much?",
            category=Category.DATA,
            expectation="something",
            reference=Query(entity="seasons", select=[Projection("salary_cap")]),
        )


def test_a_question_with_no_reference_must_explain_why():
    """Otherwise a gap is indistinguishable from an oversight."""
    with pytest.raises(ValueError, match="must say why"):
        Golden(id="x", question="How much?", category=Category.DATA, expectation="something")


def test_every_reference_query_validates_against_the_catalog():
    """Catches a question written against a field that was later renamed."""
    for golden in GOLDEN:
        if golden.reference is not None:
            golden.reference.validate()


def test_the_routed_questions_cover_every_non_data_category():
    """
    The router (task 6.1) is measured against these, so each class it must
    recognise needs at least one labelled example.
    """
    routed = {g.category for g in GOLDEN if g.reference is None}
    assert routed == {
        Category.RULES,
        Category.VALIDATION,
        Category.CONSTRAINTS,
        Category.REFUSED,
    }


@needs_data
def test_every_answerable_question_is_expressible_and_correct(conn):
    report = run_query_evals(conn)
    assert report.failed == [], f"wrong answers: {report.failed}"
    assert report.errored == [], f"did not run: {report.errored}"
    assert len(report.passed) == report.answerable


@needs_data
def test_the_grader_accepts_a_differently_written_query(conn):
    """
    The point of grading on results: a model that selects the columns in another
    order, or filters in another order, has still answered the question.
    """
    golden = next(g for g in GOLDEN if g.id == "team-committed-salary")
    assert golden.reference is not None
    reordered = Query(
        entity="contract_seasons",
        select=[Projection("salary", Agg.SUM, "sum_of_salary")],
        filters=[
            Filter("season", Op.EQ, "2026-2027"),  # reversed
            Filter("team", Op.EQ, "DEN"),
        ],
    )
    assert grade(conn, golden, reordered)


@needs_data
def test_the_grader_rejects_a_query_for_the_wrong_team(conn):
    golden = next(g for g in GOLDEN if g.id == "team-committed-salary")
    wrong = Query(
        entity="contract_seasons",
        select=[Projection("salary", Agg.SUM, "total")],
        filters=[Filter("team", Op.EQ, "BOS"), Filter("season", Op.EQ, "2026-2027")],
    )
    assert not grade(conn, golden, wrong)


@needs_data
def test_row_order_is_only_enforced_where_the_question_asked_for_it(conn):
    """
    "Who are the ten highest paid" is an ordered answer; "which teams are hard
    capped" is not. Grading the unordered one on order would fail a correct
    translation that sorted differently.
    """
    ordered = next(g for g in GOLDEN if g.id == "highest-paid-players")
    assert ordered.ordered
    assert ordered.reference is not None
    reversed_order = Query(
        entity="contract_seasons",
        select=[Projection("player"), Projection("team"), Projection("salary")],
        filters=[Filter("season", Op.EQ, "2026-2027")],
        order_by=[Order("salary", False)],
        limit=10,
    )
    assert not grade(conn, ordered, reversed_order), "order is part of this answer"

    unordered = next(g for g in GOLDEN if g.id == "teams-above-second-apron")
    assert not unordered.ordered
    assert unordered.reference is not None
    resorted = Query(
        entity="hard_cap_ceilings",
        select=[Projection("team"), Projection("trigger_category"), Projection("season")],
        filters=[Filter("apron_level", Op.EQ, "second_apron")],
        order_by=[Order("team", True)],  # descending instead of ascending
    )
    assert grade(conn, unordered, resorted), "order is not part of this answer"


@needs_data
def test_guarantee_structure_reads_unknown_rather_than_fully_guaranteed(conn):
    """
    No source carries guarantee structure. The column defaulted to 'full',
    which asserted something never read (ADR-003).
    """
    rows = conn.execute("SELECT DISTINCT guarantee_kind FROM contract_years").fetchall()
    assert [r[0] for r in rows] == ["unknown"]
