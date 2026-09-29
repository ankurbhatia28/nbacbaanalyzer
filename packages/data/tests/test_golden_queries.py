"""
Golden queries (task 2.8): real questions, end to end against the built database.

These are the questions that motivated the rescope. If the DSL cannot express
one, that is a gap to close rather than a test to weaken.
"""

from pathlib import Path

import pytest

from nbadata.db import open_readonly
from nbadata.ingest.load import load
from nbadata.query import Agg, Filter, Op, Order, Projection, Query, lookup_player, run

CSV_DIR = Path(__file__).resolve().parents[3] / "scraper" / "out"
pytestmark = pytest.mark.skipif(
    not (CSV_DIR / "contracts.csv").exists(), reason="scraper output not present"
)


@pytest.fixture(scope="module")
def conn(tmp_path_factory):
    db = tmp_path_factory.mktemp("q") / "golden.db"
    load(CSV_DIR, db)
    return open_readonly(db)


def test_how_many_players_have_bird_rights(conn):
    """The question that prompted the scope change."""
    result = run(
        conn,
        Query(
            entity="cap_holds",
            select=[Projection("bird_rights"), Projection("*", Agg.COUNT, "n")],
            filters=[Filter("bird_rights", Op.IN, ["Bird", "Early Bird", "Non-Bird"])],
            group_by=["bird_rights"],
            order_by=[Order("n", True)],
        ),
    )
    counts = {r["bird_rights"]: r["n"] for r in result.rows}
    assert set(counts) == {"Bird", "Early Bird", "Non-Bird"}
    assert counts["Bird"] > 20
    assert "SELECT" in result.sql  # the derivation is inspectable (task 7.3)


def test_which_ceilings_does_milwaukee_hold(conn):
    """Two ceilings, from two different transactions. The lower binds."""
    result = run(
        conn,
        Query(
            entity="hard_cap_ceilings",
            select=[Projection("apron_level"), Projection("trigger_category")],
            filters=[Filter("team", Op.EQ, "MIL")],
        ),
    )
    levels = {r["apron_level"] for r in result.rows}
    assert levels == {"first_apron", "second_apron"}


def test_houston_is_capped_at_the_second_apron(conn):
    result = run(
        conn,
        Query(
            entity="hard_cap_ceilings",
            select=[Projection("apron_level"), Projection("trigger_detail")],
            filters=[Filter("team", Op.EQ, "HOU")],
        ),
    )
    assert [r["apron_level"] for r in result.rows] == ["second_apron"]


def test_team_committed_salary_for_a_season(conn):
    result = run(
        conn,
        Query(
            entity="contract_seasons",
            select=[Projection("team"), Projection("salary", Agg.SUM, "total")],
            filters=[Filter("season", Op.EQ, "2026-2027")],
            group_by=["team"],
            order_by=[Order("total", True)],
            limit=3,
        ),
    )
    assert result.row_count == 3
    assert result.rows[0]["total"] > 200_000_000


def test_who_has_a_player_option_in_a_future_season(conn):
    result = run(
        conn,
        Query(
            entity="contract_seasons",
            select=[Projection("player"), Projection("salary")],
            filters=[Filter("option_kind", Op.EQ, "player"), Filter("season", Op.EQ, "2027-2028")],
            order_by=[Order("salary", True)],
            limit=5,
        ),
    )
    assert result.row_count > 0


def test_higher_max_criteria_award_counts(conn):
    """All-NBA / DPOY / MVP only -- All-Star is deliberately not collected."""
    result = run(
        conn,
        Query(
            entity="awards",
            select=[Projection("award"), Projection("*", Agg.COUNT, "n")],
            group_by=["award"],
        ),
    )
    awards = {r["award"] for r in result.rows}
    assert awards == {"All-NBA", "DPOY", "MVP"}


def test_trade_exceptions_show_remaining_not_just_original(conn):
    result = run(
        conn,
        Query(
            entity="trade_exceptions",
            select=[Projection("team"), Projection("amount"), Projection("available")],
            filters=[Filter("available", Op.NOT_NULL)],
            limit=5,
        ),
    )
    assert result.row_count > 0


def test_player_lookup_returns_candidates_not_a_guess(conn):
    matches = lookup_player(conn, "Nikola Jokić")
    assert matches and matches[0].display_name == "Nikola Jokić"
    assert len(lookup_player(conn, "williams")) > 1  # ambiguous -> clarify, never pick


def test_forfeited_picks_come_from_the_override_not_the_scrape(conn):
    """
    Superseded the earlier "no forfeiture data" guard, deliberately.

    No scraped source represents forfeiture, so these five rows exist only
    because data/overrides/pick_overrides.csv asserts them with a citation.
    """
    result = run(
        conn,
        Query(
            entity="draft_picks",
            select=[Projection("year"), Projection("team"), Projection("original_team")],
            filters=[Filter("forfeited", Op.EQ, 1)],
            order_by=[Order("year")],
        ),
    )
    assert result.row_count == 5
    assert [r["year"] for r in result.rows] == [2029, 2030, 2031, 2032, 2033]
    assert all(r["team"] == "LAC" for r in result.rows)


def test_the_clippers_still_hold_firsts_in_three_penalty_years(conn):
    """
    The precision the override buys. RealGM's counts across 2029-2033 are
    1/0/1/0/1: their own firsts are gone in four of those years and the Indiana
    pick in the fifth, but Toronto firsts in 2031 and 2033 and their own in 2029
    mean the bare years are non-consecutive -- and so Stepien-legal.
    """
    held = {}
    for year in range(2029, 2034):
        result = run(
            conn,
            Query(
                entity="draft_picks",
                select=[Projection("*", Agg.COUNT, "n")],
                filters=[
                    Filter("year", Op.EQ, year),
                    Filter("round", Op.EQ, 1),
                    Filter("team", Op.EQ, "LAC"),
                    Filter("forfeited", Op.EQ, 0),
                ],
            ),
        )
        held[year] = result.scalar()
    assert held == {2029: 1, 2030: 0, 2031: 1, 2032: 0, 2033: 1}
    bare = [y for y, n in held.items() if n == 0]
    assert not any(y + 1 in bare for y in bare), "bare years must not be consecutive"
