"""
The cap sheet (7.5). The property that matters is that it cannot disagree with
the engine: every total is the sum of the lines shown, line by line, for every
team -- so a reader can check any figure by adding up what is in front of them.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nbadata.db import open_readonly
from nbadata.ingest.load import load as load_csvs
from nbadata.sheet import cap_sheet
from nbadata.state import MissingDataError, team_state, teams

CSV_DIR = Path(__file__).resolve().parents[3] / "scraper" / "out"
pytestmark = pytest.mark.skipif(
    not (CSV_DIR / "contracts.csv").exists(), reason="scraper output not present"
)


@pytest.fixture(scope="module")
def league(tmp_path_factory):
    path = tmp_path_factory.mktemp("sheet") / "league.db"
    load_csvs(CSV_DIR, path)
    return open_readonly(path)


def test_every_total_is_the_sum_of_the_lines_shown(league):
    for t in teams(league):
        sheet = cap_sheet(league, t.key)
        state = team_state(league, t.key)
        assert sheet.totals["cap"] == sum(line.cap for line in sheet.lines) == state.cap_salary()
        assert sheet.totals["apron"] == sum(line.apron for line in sheet.lines)
        assert sheet.totals["apron"] == state.apron_team_salary()
        assert sheet.status == state.apron_status().value


def test_holds_count_toward_the_cap_but_not_the_aprons_except_a_qualifying_offer(league):
    """Art. VII §2(e)(1)(iv) and (v), shown per line rather than only in the total."""
    holds = {line.player: line for line in cap_sheet(league, "DEN").lines if line.kind == "hold"}
    watson = holds.pop("peyton watson")
    assert (watson.cap, watson.apron) == (13_069_428, 6_534_714)
    assert all(line.apron == 0 and line.cap == line.amount for line in holds.values())


def test_dead_money_is_a_line_and_counts_everywhere(league):
    lines = cap_sheet(league, "MIL").lines
    (lillard,) = [line for line in lines if line.player == "damian lillard"]
    assert lillard.kind == "dead"
    assert lillard.cap == lillard.apron == 22_516_603


def test_a_binding_ceiling_carries_its_room_and_triggers(league):
    sheet = cap_sheet(league, "MIL")
    assert sheet.ceiling is not None
    assert sheet.ceiling["level"] == "first_apron"
    assert sheet.ceiling["room"] == sheet.thresholds["first_apron"] - sheet.totals["apron"]
    assert sheet.ceiling["triggers"]


def test_trade_exceptions_are_checked_for_expiry_not_trusted(league):
    """The archived rows predate the payroll; a dated one is compared, an undated one is not."""
    sheet = cap_sheet(league, "MIL")
    dated = [t for t in sheet.trade_exceptions if t.expires == "2027-07-06"]
    assert dated and all(t.expired is False for t in dated)
    assert all(t.expired is None for t in sheet.trade_exceptions if t.expires == "End-of-Season")


def test_names_are_shown_never_join_keys(league):
    for t in teams(league):
        for line in cap_sheet(league, t.key).lines:
            assert line.player is None or line.name, (t.key, line.player)


def test_unknowns_are_said_once_not_left_blank(league):
    assert any("unknown" in w for w in cap_sheet(league, "BOS").warnings)


def test_an_unknown_team_is_an_error(league):
    with pytest.raises(MissingDataError):
        cap_sheet(league, "XYZ")
