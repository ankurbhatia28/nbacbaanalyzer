"""
Trades checked against the league database (7.4).

Real teams, real contracts. These pin the two engine defects the trade builder
exposed -- a barred exception used anyway, and structuring left unused -- and
the shape the builder relies on: each side's after-position is its before
minus what it sends plus what it receives.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from nbadata.db import open_readonly
from nbadata.ingest.load import load as load_csvs
from nbadata.state import MissingDataError
from nbadata.trades import Move, TradeError, check, to_json

CSV_DIR = Path(__file__).resolve().parents[3] / "scraper" / "out"
pytestmark = pytest.mark.skipif(
    not (CSV_DIR / "contracts.csv").exists(), reason="scraper output not present"
)
WHEN = date(2026, 10, 3)


@pytest.fixture(scope="module")
def league(tmp_path_factory):
    path = tmp_path_factory.mktemp("trades") / "league.db"
    load_csvs(CSV_DIR, path)
    return open_readonly(path)


def run(league, *moves):
    return to_json(*check(league, [Move(*m) for m in moves], WHEN))


def side(result, team):
    return next(s for s in result["sides"] if s["team"] == team)


def test_an_exception_is_barred_when_it_would_leave_the_team_above_its_apron(league):
    """
    Denver takes back $9.2M more than it sends, which only the Expanded
    exception covers -- and using it to finish over the first apron is barred
    by Art. VII 2(e)(2)(i)(A). This was called legal before 7.4.
    """
    got = run(
        league,
        ("jamal murray", "DEN", "DAL"),
        ("kyrie irving", "DAL", "DEN"),
        ("pj washington", "DAL", "DEN"),
    )
    assert got["legal"] is False
    (barred,) = side(got, "DEN")["violations"]
    assert barred["code"] == "apron_transaction_barred"
    assert barred["citation"] == "Art. VII §2(e)(2)(i)(A)"
    assert "first apron" in barred["detail"]
    assert side(got, "DAL")["violations"] == []


def test_a_legal_trade_says_which_side_it_hard_caps(league):
    got = run(league, ("christian braun", "DEN", "DAL"), ("pj washington", "DAL", "DEN"))
    assert got["legal"] is True
    assert any(n.startswith("DAL:") and "row E" in n for n in got["notes"])


def test_each_side_after_is_its_before_less_what_it_sends_plus_what_it_receives(league):
    got = run(league, ("aaron gordon", "DEN", "DAL"), ("pj washington", "DAL", "DEN"))
    for s in got["sides"]:
        assert s["after"]["apron"] == s["before"]["apron"] - s["outgoing"] + s["incoming"]
        assert s["after"]["standard_contracts"] == (
            s["before"]["standard_contracts"] - len(s["sends"]) + len(s["receives"])
        )


def test_an_unknown_kicker_is_an_assumption_on_the_verdict_not_a_silent_zero(league):
    """ADR-003: every contract acquired has an unknown kicker, assumed absent, and says so."""
    got = run(league, ("aaron gordon", "DEN", "DAL"), ("pj washington", "DAL", "DEN"))
    assert got["conditional"] is True
    assert {a["subject"] for a in got["assumptions"]} == {"aaron gordon", "pj washington"}
    assert got["unsourced"]


@pytest.mark.parametrize(
    ("moves", "message"),
    [
        ([], "Add a player"),
        ([("jamal murray", "DEN", "DEN")], "at least two teams"),
        ([("jamal murray", "DAL", "DEN")], "not under contract with DAL"),
        (
            [("jamal murray", "DEN", "DAL"), ("jamal murray", "DEN", "BOS")],
            "twice",
        ),
    ],
)
def test_a_trade_that_is_not_one_is_refused_with_a_sentence(league, moves, message):
    with pytest.raises(TradeError, match=message):
        run(league, *moves)


def test_an_unknown_team_is_missing_data(league):
    with pytest.raises(MissingDataError):
        run(league, ("jamal murray", "DEN", "XYZ"))
