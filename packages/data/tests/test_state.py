"""
The bridge from the league database to the engine (Phase 7).

Two kinds of test. Mapping rules -- dates, hold labels -- run everywhere. The
whole-team checks need the scraper output, and pin the properties that make a
`TeamState` trustworthy: every gap stays an explicit unknown, holds land where
§2(e)(1) puts them, and every team loads.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from engine.apron import ApronLevel
from engine.contract import ContractType, GuaranteeType
from engine.holds import HoldKind
from nbadata.db import open_readonly
from nbadata.ingest.load import load as load_csvs
from nbadata.state import MissingDataError, _date, hold_kind, team_state, teams

CSV_DIR = Path(__file__).resolve().parents[3] / "scraper" / "out"
needs_data = pytest.mark.skipif(
    not (CSV_DIR / "contracts.csv").exists(), reason="scraper output not present"
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-09-29", date(2026, 9, 29)),
        ("October 21, 2024", date(2024, 10, 21)),
        ("7/6/2026", date(2026, 7, 6)),
        ("", None),
        (None, None),
        ("not a date", None),
    ],
)
def test_dates_in_every_format_the_sources_write(raw, expected):
    assert _date(raw) == expected


@pytest.mark.parametrize(
    ("label", "kind"),
    [
        ("Restricted Bird", HoldKind.QUALIFYING_OFFER),
        ("Restricted Non-Bird", HoldKind.QUALIFYING_OFFER),
        ("1st Round Pick", HoldKind.DRAFT_PICK),
        ("Draft Pick", HoldKind.DRAFT_PICK),
        ("Two-Way", HoldKind.TWO_WAY),
        ("Bird", HoldKind.FREE_AGENT),
        ("Non-Bird", HoldKind.FREE_AGENT),
        (None, HoldKind.FREE_AGENT),
    ],
)
def test_restricted_free_agents_are_held_as_qualifying_offers(label, kind):
    """That is how §2(e)(1)(v) counts them toward the aprons."""
    assert hold_kind(label) is kind


@pytest.fixture(scope="module")
def league(tmp_path_factory):
    path = tmp_path_factory.mktemp("state") / "league.db"
    load_csvs(CSV_DIR, path)
    return open_readonly(path)


@needs_data
def test_every_team_loads(league):
    loaded = [team_state(league, t.key) for t in teams(league)]
    assert len(loaded) == 30
    assert all(s.contracts for s in loaded)


@needs_data
def test_gaps_in_the_data_stay_unknown_rather_than_defaulted(league):
    """ADR-003, for every field the sources do not carry."""
    state = team_state(league, "DEN")
    contract = state.contracts[0]
    assert contract.contract_type is ContractType.UNKNOWN
    assert contract.trade_kicker_pct.is_unknown
    assert contract.no_trade_clause.is_unknown
    assert {y.guarantee.kind for c in state.contracts for y in c.years} == {GuaranteeType.UNKNOWN}


@needs_data
def test_a_restricted_free_agent_counts_toward_the_aprons_at_his_qualifying_offer(league):
    """Denver holds Peyton Watson's rights: a $13.1M hold, a $6.5M qualifying offer."""
    state = team_state(league, "DEN")
    (watson,) = [h for h in state.cap_holds if h.player_id == "peyton watson"]
    assert watson.kind is HoldKind.QUALIFYING_OFFER
    assert watson.qualifying_offer == 6_534_714
    others = sum(h.amount for h in state.cap_holds if h is not watson)
    assert state.cap_salary() - state.apron_team_salary() == watson.amount - 6_534_714 + others


@needs_data
def test_hard_cap_ceilings_load_with_their_level_and_trigger(league):
    """SalarySwish gives the level and the transaction, not the row or the date."""
    ceilings = team_state(league, "MIN").ceilings.ceilings
    assert {c.level for c in ceilings} == {ApronLevel.FIRST, ApronLevel.SECOND}
    assert all(c.row is None and c.effective_date is None for c in ceilings)
    assert any("Cash Traded" in (c.source_transaction or "") for c in ceilings)


@needs_data
def test_an_unknown_team_is_an_error_not_an_empty_team(league):
    with pytest.raises(MissingDataError):
        team_state(league, "XYZ")


@needs_data
def test_dead_money_counts_toward_the_aprons(league):
    """Milwaukee carries $22.5M of dead cap for Damian Lillard, and the aprons see it."""
    state = team_state(league, "MIL")
    assert any(d.player_id == "damian lillard" for d in state.dead_money)
    dead = sum(d.amount for d in state.dead_money)
    assert dead == 22_516_603 + 666_667
    assert state.apron_team_salary() >= state.committed_salary() + dead


@needs_data
def test_no_team_sits_above_its_own_hard_cap_as_the_engine_sees_it(league):
    """
    D18's invariant, asked of `TeamState` rather than SQL: the bridge and the
    ingest test must agree on what Apron Team Salary includes.
    """
    for t in teams(league):
        room = team_state(league, t.key).room_below_ceiling()
        assert room is None or room >= 0, t.key
