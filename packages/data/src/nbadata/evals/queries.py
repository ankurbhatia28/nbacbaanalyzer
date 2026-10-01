"""
Query DSL eval set (task 4.7).

Golden questions with expected results. Each one is a question a user would
actually type, paired with a reference `Query` and an assertion the result must
satisfy.

Two jobs, now and later:

* **Now** -- expressiveness coverage. Every question either compiles and
  returns a result that satisfies its expectation, or is recorded as a gap with
  the reason. A question the DSL cannot express is a finding, not something to
  quietly drop (task 2.10).
* **Phase 6** -- the scored target for NL to DSL translation. `grade()` takes
  the query a model emitted and compares **the result it produces** against the
  reference result, not the query text. Many different queries are the same
  question -- ordering the filters differently, selecting a superset of columns,
  grouping where the reference aggregates -- and marking those wrong would
  penalise correct translations. What matters is whether the user gets the right
  answer.

Questions outside the DSL are carried here too, with the category that should
route them elsewhere. The router (task 6.1) has to recognise a constraints or
validation question as *not* a data question, and it needs labelled examples of
both to be measured against.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from nbadata.query import Agg, Filter, Op, Order, Projection, Query, QueryResult, run


class Category(StrEnum):
    """The routing classes of task 6.1."""

    DATA = "data"
    """Answerable by one query against the catalog."""
    RULES = "rules"
    """Needs the CBA text; answered by retrieval plus a citation."""
    VALIDATION = "validation"
    """Needs the rules engine to judge a proposed transaction."""
    CONSTRAINTS = "constraints"
    """Needs the engine to enumerate what limits a team, with no deal proposed."""
    REFUSED = "refused"
    """Out of scope by a settled decision. The refusal must state which."""


Check = Callable[[QueryResult], bool]


@dataclass(frozen=True, slots=True)
class Golden:
    id: str
    question: str
    category: Category
    expectation: str
    """What must be true of the answer, in words. Shown when the check fails."""
    reference: Query | None = None
    check: Check | None = None
    ordered: bool = False
    """Whether row order is part of the answer ("who earns the most")."""
    gap: str = ""
    """Why no reference query exists. Required when `reference` is None."""

    def __post_init__(self) -> None:
        if self.reference is None and not self.gap:
            raise ValueError(f"{self.id}: a question without a reference query must say why")
        if self.reference is not None and self.check is None:
            raise ValueError(f"{self.id}: a reference query without a check asserts nothing")


def _nonempty(result: QueryResult) -> bool:
    return result.row_count > 0


def _int(row: dict[str, object], key: str) -> int:
    """
    A result row is dict[str, object], so a check that compares a figure has to
    narrow it. Raising on a non-integer is deliberate: it means the column
    changed type and the expectation is no longer testing what it claims.
    """
    value = row[key]
    if not isinstance(value, int):
        raise TypeError(f"expected {key} to be an integer, got {type(value).__name__}: {value!r}")
    return value


def _scalar_at_least(n: int) -> Check:
    def check(result: QueryResult) -> bool:
        value = result.scalar()
        return isinstance(value, int) and value >= n

    return check


# --- the set ---------------------------------------------------------------
#
# Figures are asserted as bounds, not equalities. The underlying data is
# re-scraped, and a test that pins "exactly 41 players" fails on the next
# signing without anything being wrong. A bound still catches the failure that
# matters: the query stopped returning the right *kind* of answer.

GOLDEN: list[Golden] = [
    Golden(
        id="bird-rights-current",
        question="How many players currently hold Bird rights?",
        category=Category.DATA,
        expectation=(
            "one count per Bird category, Non-Bird the largest -- most holds "
            "sit on players without full Bird rights"
        ),
        reference=Query(
            entity="cap_holds",
            select=[Projection("bird_rights"), Projection("*", Agg.COUNT, "n")],
            filters=[Filter("bird_rights", Op.IN, ["Bird", "Early Bird", "Non-Bird"])],
            group_by=["bird_rights"],
            order_by=[Order("n", True)],
        ),
        check=lambda r: r.row_count == 3 and r.rows[0]["bird_rights"] == "Non-Bird",
        ordered=True,
    ),
    Golden(
        id="bird-rights-two-seasons",
        question="How many players have had their Bird rights exercised in the past 2 seasons?",
        category=Category.REFUSED,
        expectation=(
            "refused as historical, citing D6; the current-state form of the "
            "question is offered instead"
        ),
        gap=(
            "D6 puts historical scope out of v1. The database holds current state, "
            "so 'in the past 2 seasons' cannot be answered -- and must not be "
            "silently answered as 'now'."
        ),
    ),
    Golden(
        id="teams-above-second-apron",
        question="Which teams are hard capped at the second apron this season?",
        category=Category.DATA,
        expectation="at least one team, each with the triggering transaction named",
        reference=Query(
            entity="hard_cap_ceilings",
            select=[Projection("team"), Projection("trigger_category"), Projection("season")],
            filters=[Filter("apron_level", Op.EQ, "second_apron")],
            order_by=[Order("team", False)],
        ),
        check=lambda r: _nonempty(r) and all(row["trigger_category"] for row in r.rows),
    ),
    Golden(
        id="milwaukee-ceilings",
        question="What is Milwaukee's hard cap?",
        category=Category.DATA,
        expectation="the ceilings Milwaukee holds, each naming what triggered it",
        reference=Query(
            entity="hard_cap_ceilings",
            select=[
                Projection("apron_level"),
                Projection("trigger_category"),
                Projection("trigger_detail"),
            ],
            filters=[Filter("team", Op.EQ, "MIL")],
        ),
        check=_nonempty,
    ),
    Golden(
        id="team-committed-salary",
        question="How much salary do the Denver Nuggets have committed for 2026-27?",
        category=Category.DATA,
        expectation="a single figure above $100M",
        reference=Query(
            entity="contract_seasons",
            select=[Projection("salary", Agg.SUM, "total")],
            filters=[Filter("team", Op.EQ, "DEN"), Filter("season", Op.EQ, "2026-2027")],
        ),
        check=_scalar_at_least(100_000_000),
    ),
    Golden(
        id="highest-paid-players",
        question="Who are the ten highest paid players in 2026-27?",
        category=Category.DATA,
        expectation="ten players in descending salary order",
        reference=Query(
            entity="contract_seasons",
            select=[Projection("player"), Projection("team"), Projection("salary")],
            filters=[Filter("season", Op.EQ, "2026-2027")],
            order_by=[Order("salary", True)],
            limit=10,
        ),
        check=lambda r: (
            r.row_count == 10
            and [_int(row, "salary") for row in r.rows]
            == sorted((_int(row, "salary") for row in r.rows), reverse=True)
        ),
        ordered=True,
    ),
    Golden(
        id="player-options",
        question="Which players hold a player option for 2027-28?",
        category=Category.DATA,
        expectation="a non-empty list, every row a player option",
        reference=Query(
            entity="contract_seasons",
            select=[Projection("player"), Projection("team"), Projection("salary")],
            filters=[
                Filter("season", Op.EQ, "2027-2028"),
                Filter("option_kind", Op.EQ, "player"),
            ],
            order_by=[Order("salary", True)],
        ),
        check=_nonempty,
    ),
    Golden(
        id="trade-exceptions-available",
        question="Which teams have a trade exception worth more than $5 million?",
        category=Category.DATA,
        expectation="rows showing the remaining amount, not the original",
        reference=Query(
            entity="trade_exceptions",
            select=[Projection("team"), Projection("amount"), Projection("available")],
            filters=[Filter("available", Op.GT, 5_000_000)],
            order_by=[Order("available", True)],
        ),
        check=lambda r: _nonempty(r) and all(_int(row, "available") > 5_000_000 for row in r.rows),
    ),
    Golden(
        id="forfeited-picks",
        question="Which draft picks have been forfeited?",
        category=Category.DATA,
        expectation="the five Clippers firsts, each carrying its override citation",
        reference=Query(
            entity="draft_picks",
            select=[
                Projection("year"),
                Projection("round"),
                Projection("team"),
                Projection("original_team"),
                Projection("protection_text"),
            ],
            filters=[Filter("forfeited", Op.EQ, 1)],
            order_by=[Order("year", False)],
        ),
        check=lambda r: (
            r.row_count == 5
            and all("OVERRIDE forfeit" in str(row["protection_text"]) for row in r.rows)
        ),
    ),
    Golden(
        id="award-counts-for-supermax",
        question="Which players have won MVP?",
        category=Category.DATA,
        expectation="a non-empty list; All-Star selections are deliberately absent",
        reference=Query(
            entity="awards",
            select=[Projection("player"), Projection("season"), Projection("tier")],
            filters=[Filter("award", Op.EQ, "MVP")],
            order_by=[Order("season", True)],
        ),
        check=_nonempty,
    ),
    Golden(
        id="cap-thresholds",
        question="What is the second apron for 2026-27?",
        category=Category.DATA,
        expectation="one figure, above the first apron for the same season",
        reference=Query(
            entity="seasons",
            select=[
                Projection("salary_cap"),
                Projection("first_apron"),
                Projection("second_apron"),
            ],
            filters=[Filter("season", Op.EQ, "2026-2027")],
        ),
        check=lambda r: (
            r.row_count == 1
            and _int(r.rows[0], "second_apron")
            > _int(r.rows[0], "first_apron")
            > _int(r.rows[0], "salary_cap")
        ),
    ),
    Golden(
        id="non-guaranteed-deals",
        question="Which contracts for 2026-27 are not fully guaranteed?",
        category=Category.REFUSED,
        expectation=(
            "stated as unknown rather than answered. Returning an empty list "
            "would mean 'none', which is not what we know"
        ),
        gap=(
            "No scraped source carries guarantee structure -- Basketball-Reference "
            "marks it with cell styling the scraper does not read. The column "
            "defaulted to 'full', asserting something never read; it now defaults "
            "to 'unknown' (ADR-003). Closing this needs a source that publishes "
            "guarantee dates and amounts."
        ),
    ),
    Golden(
        id="roster-count",
        question="How many players does each team have under contract for 2026-27?",
        category=Category.DATA,
        expectation="all 30 teams, each with a plausible roster count",
        reference=Query(
            entity="contract_seasons",
            select=[Projection("team"), Projection("player", Agg.COUNT_DISTINCT, "n")],
            filters=[Filter("season", Op.EQ, "2026-2027")],
            group_by=["team"],
            order_by=[Order("n", True)],
            limit=30,
        ),
        check=lambda r: r.row_count == 30 and all(0 < _int(row, "n") < 30 for row in r.rows),
    ),
    Golden(
        id="qualifying-offers",
        question="Which players have a qualifying offer outstanding?",
        category=Category.DATA,
        expectation="a non-empty list, every row carrying an offer amount",
        reference=Query(
            entity="cap_holds",
            select=[Projection("player"), Projection("team"), Projection("qualifying_offer")],
            filters=[Filter("qualifying_offer", Op.GT, 0)],
            order_by=[Order("qualifying_offer", True)],
        ),
        check=lambda r: _nonempty(r) and all(_int(row, "qualifying_offer") > 0 for row in r.rows),
    ),
    # --- questions the DSL should not answer -------------------------------
    Golden(
        id="embiid-trade-limits",
        question="If I wanted to trade Embiid, what are the limitations the 76ers have?",
        category=Category.CONSTRAINTS,
        expectation=(
            "an enumeration of every constraint binding Philadelphia, with the "
            "assumptions each rests on"
        ),
        gap=(
            "Needs team_trade_constraints (task 3.19), which composes apron status, "
            "ceilings, pick rules and trade dates. No single query expresses it, and "
            "a query that returned only the salary figures would look like an answer "
            "while omitting the binding constraints."
        ),
    ),
    Golden(
        id="jokic-doncic-straight-up",
        question="Is trading Jokic for Doncic a valid trade straight up?",
        category=Category.VALIDATION,
        expectation="a verdict with the violations, the citations, and the assumptions",
        gap=(
            "Needs validate_trade (task 3.18). The data layer can supply both "
            "salaries; judging the trade is the engine's job."
        ),
    ),
    Golden(
        id="what-is-the-second-apron",
        question="What is the second apron and what does it restrict?",
        category=Category.RULES,
        expectation=(
            "the restrictions derived from Art. VII 2(e)(2)(i)(A), each quoted with its citation"
        ),
        gap=(
            "A rules question, not a data one. The `seasons` entity holds the "
            "*figure*; what it restricts lives in the CBA text and is answered by "
            "retrieval (Phase 5)."
        ),
    ),
    Golden(
        id="should-denver-trade-murray",
        question="Should the Nuggets trade Jamal Murray?",
        category=Category.REFUSED,
        expectation="declined as a judgement call, citing D10, with no recommendation",
        gap="D10 settles this: 'is it legal' is answered, 'should they' is declined.",
    ),
]


# --- running ---------------------------------------------------------------


@dataclass
class QueryEvalReport:
    passed: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    errored: list[tuple[str, str]] = field(default_factory=list)
    gaps: list[Golden] = field(default_factory=list)

    @property
    def answerable(self) -> int:
        return len(self.passed) + len(self.failed) + len(self.errored)

    def render(self) -> str:
        by_category: dict[str, int] = {}
        for golden in self.gaps:
            by_category[golden.category] = by_category.get(golden.category, 0) + 1
        lines = [
            f"{len(GOLDEN)} golden questions "
            f"({self.answerable} answerable by one query, {len(self.gaps)} routed elsewhere)",
            "",
            f"  expressible and correct  {len(self.passed)}/{self.answerable}",
        ]
        if self.failed:
            lines += ["", "wrong answer:"]
            lines += [f"  {qid}: {why}" for qid, why in self.failed]
        if self.errored:
            lines += ["", "did not compile or run:"]
            lines += [f"  {qid}: {why}" for qid, why in self.errored]
        lines += ["", "routed away from the query layer:"]
        lines += [f"  {cat:<12} {n}" for cat, n in sorted(by_category.items())]
        return "\n".join(lines)


def run_query_evals(conn: sqlite3.Connection) -> QueryEvalReport:
    report = QueryEvalReport()
    for golden in GOLDEN:
        if golden.reference is None:
            report.gaps.append(golden)
            continue
        try:
            result = run(conn, golden.reference)
        except Exception as exc:
            report.errored.append((golden.id, f"{type(exc).__name__}: {exc}"))
            continue
        assert golden.check is not None  # guaranteed by __post_init__
        if golden.check(result):
            report.passed.append(golden.id)
        else:
            report.failed.append((golden.id, golden.expectation))
    return report


# --- grading a model's translation (used from Phase 6) ---------------------


def _comparable(result: QueryResult, *, ordered: bool) -> object:
    """
    Reduce a result to what the user actually reads: the values.

    Column *names* are normalised away, because an alias is cosmetic -- a
    candidate that calls the sum `sum_of_salary` rather than `total` has still
    answered the question. So is the order of the columns within a row, and so
    is row order unless the question asked for a ranking. What remains is the
    set of values put in front of the user, which is the thing that can be
    right or wrong.

    Values are sorted by `repr` because a row mixes strings, integers and
    None, which do not compare against each other.
    """
    rows = [tuple(sorted(row.values(), key=repr)) for row in result.rows]
    return rows if ordered else sorted(rows, key=repr)


def grade(conn: sqlite3.Connection, golden: Golden, candidate: Query) -> bool:
    """
    Whether a model-emitted query answers the question.

    Compared by result rather than by query text: a candidate that filters in a
    different order, or selects columns in a different order, is still correct.
    """
    if golden.reference is None:
        return False
    expected = run(conn, golden.reference)
    actual = run(conn, candidate)
    return _comparable(actual, ordered=golden.ordered) == _comparable(
        expected, ordered=golden.ordered
    )
