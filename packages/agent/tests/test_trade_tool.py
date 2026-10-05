"""
The chat's trade verdict comes from the engine (validate_trade).

Needs only the league database, which is built from the tracked scraper
output, so unlike test_tools.py this runs in CI without the CBA PDF.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agent.answer import Verdict, _collect
from agent.tools import Resources, call
from nbadata.db import open_readonly
from nbadata.ingest.load import load as load_csvs

CSV_DIR = Path(__file__).resolve().parents[3] / "scraper" / "out"
pytestmark = pytest.mark.skipif(
    not (CSV_DIR / "contracts.csv").exists(), reason="scraper output not present"
)

MURRAY_FOR_IRVING_AND_WASHINGTON = {
    "moves": [
        {"player": "jamal murray", "from_team": "DEN", "to_team": "DAL"},
        {"player": "kyrie irving", "from_team": "DAL", "to_team": "DEN"},
        {"player": "pj washington", "from_team": "DAL", "to_team": "DEN"},
    ]
}


@pytest.fixture(scope="module")
def res(tmp_path_factory: pytest.TempPathFactory) -> Resources:
    db = tmp_path_factory.mktemp("trade") / "league.db"
    load_csvs(CSV_DIR, db)
    # The trade tool reads no CBA text; an empty index stands in for it.
    return Resources(league=open_readonly(db), cba=sqlite3.connect(":memory:"), base_season_cap=0)


def test_the_verdict_is_the_engines(res: Resources) -> None:
    """The 7.4 case: legal by matching alone, barred by the apron row (§2(e)(2)(i)(A))."""
    result = call(res, "validate_trade", MURRAY_FOR_IRVING_AND_WASHINGTON)
    assert result["ok"] is True
    assert result["legal"] is False
    denver = next(s for s in result["sides"] if s["team"] == "DEN")
    assert [(v["code"], v["citation"]) for v in denver["violations"]] == [
        ("apron_transaction_barred", "Art. VII §2(e)(2)(i)(A)")
    ]


def test_a_trade_that_is_not_one_is_an_error_the_model_can_report(res: Resources) -> None:
    result = call(
        res,
        "validate_trade",
        {"moves": [{"player": "jamal murray", "from_team": "BOS", "to_team": "DAL"}]},
    )
    assert result["ok"] is False
    assert "not under contract with BOS" in result["error"]


def test_an_unknown_team_is_an_error_not_an_exception(res: Resources) -> None:
    result = call(
        res,
        "validate_trade",
        {"moves": [{"player": "jamal murray", "from_team": "DEN", "to_team": "XYZ"}]},
    )
    assert result["ok"] is False


def test_its_salaries_are_sourced_and_its_assumptions_reach_the_card(res: Resources) -> None:
    """
    Figures quoted from the verdict are not fabrications, and a verdict that
    rests on assumed-absent kickers has to say so (ADR-003).
    """
    result = call(res, "validate_trade", MURRAY_FOR_IRVING_AND_WASHINGTON)
    verdict = Verdict(question="q")
    sourced: set[str] = set()
    _collect(result, verdict, sourced, set())

    denver = next(s for s in result["sides"] if s["team"] == "DEN")
    assert f"{denver['incoming']:,}" in sourced
    assert any("trade_kicker_pct assumed" in a for a in verdict.assumptions)
    assert any("no-trade clauses" in a for a in verdict.assumptions)
