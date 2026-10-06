"""
Cap space comes from the engine's totals (team_cap_position), not from sums.

Needs only the league database, so it runs in CI without the CBA PDF.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from agent.answer import Verdict, _collect
from agent.tools import Resources, call
from nbadata import sheet
from nbadata.db import open_readonly
from nbadata.ingest.load import load as load_csvs

CSV_DIR = Path(__file__).resolve().parents[3] / "scraper" / "out"
pytestmark = pytest.mark.skipif(
    not (CSV_DIR / "contracts.csv").exists(), reason="scraper output not present"
)


@pytest.fixture(scope="module")
def res(tmp_path_factory: pytest.TempPathFactory) -> Resources:
    db = tmp_path_factory.mktemp("cap") / "league.db"
    load_csvs(CSV_DIR, db)
    return Resources(league=open_readonly(db), cba=sqlite3.connect(":memory:"), base_season_cap=0)


def test_every_team_in_one_call_most_room_first(res: Resources) -> None:
    result = call(res, "team_cap_position", {})
    assert result["ok"]
    room = [t["below_salary_cap"] for t in result["teams"]]
    assert len(room) == 30
    assert room == sorted(room, reverse=True)


def test_the_figures_are_the_cap_sheets(res: Resources) -> None:
    [den] = call(res, "team_cap_position", {"teams": ["den"]})["teams"]
    got = sheet.cap_sheet(res.league, "DEN")
    assert den["cap_salary"] == got.totals["cap"]
    assert den["apron_salary"] == got.totals["apron"]
    assert den["status"] == got.status
    assert den["below_salary_cap"] == got.thresholds["salary_cap"] - got.totals["cap"]
    assert den["below_second_apron"] == got.thresholds["second_apron"] - got.totals["apron"]


def test_an_unknown_team_is_an_error_for_the_model(res: Resources) -> None:
    result = call(res, "team_cap_position", {"teams": ["XYZ"]})
    assert result["ok"] is False
    assert "XYZ" in result["error"]


def test_its_figures_count_as_sourced(res: Resources) -> None:
    result = call(res, "team_cap_position", {"teams": ["DEN"]})
    sourced: set[str] = set()
    _collect(result, Verdict(question="q"), sourced, set())
    [den] = result["teams"]
    assert f"{den['cap_salary']:,}" in sourced
    assert f"{result['thresholds']['salary_cap']:,}" in sourced
