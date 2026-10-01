"""
Constraint enumeration (task 3.19) — the Embiid question.

"If I wanted to trade X, what are the limitations?" has no deal to validate, so
these tests check that the enumeration is complete in the ways that matter: the
apron rows the team may not use, which picks it may move, how much it can take
back, and what it had to assume.
"""

from datetime import date

import pytest

from engine.apron import RestrictionRow
from engine.citations import TRANSACTION_PROHIBITION, TRANSACTION_RESTRICTIONS
from engine.fixtures.picks import forfeited_firsts
from engine.fixtures.season import SEASON_2026_27
from engine.fixtures.shells import (
    capped_below_ceiling,
    room_team,
    second_apron_uncapped,
)
from engine.roster import STANDARD_MAX, STANDARD_MIN, RosterState
from engine.validate import team_trade_constraints

BASE_CAP = 136_021_000
WHEN = date(2026, 11, 1)


def kinds(report) -> list[str]:
    return [c.kind for c in report.constraints]


def detail_for(report, kind: str) -> str:
    return " | ".join(c.detail for c in report.constraints if c.kind == kind)


def test_a_second_apron_team_is_told_every_row_it_may_not_use():
    """
    The substance of the answer. Being over an apron does not stop a team
    trading; it stops it trading in particular ways, and the team needs the list.
    """
    report = team_trade_constraints(second_apron_uncapped(), as_of=WHEN)
    barred = detail_for(report, "apron_restriction")
    assert "aggregating two or more contracts" in barred
    assert "send cash to another team" in barred
    assert "Taxpayer Mid-Level" in barred
    assert "Expanded Traded Player Exception" in barred


def test_a_room_team_is_told_that_no_apron_restriction_applies():
    """Silence would be ambiguous: no constraints found reads as none checked."""
    report = team_trade_constraints(room_team(), as_of=WHEN)
    assert "no apron transaction restrictions apply" in detail_for(report, "apron_restriction")


def test_the_prohibition_is_cited_not_the_ceiling():
    """
    2(e)(2)(i)(A) bars the transaction; (i)(B) is the ceiling that attaches
    afterwards. A refusal to permit must point at (A), or the reader is sent to
    the wrong rule.
    """
    report = team_trade_constraints(second_apron_uncapped(), as_of=WHEN)
    cites = {
        c.citation.section
        for c in report.constraints
        if c.kind == "apron_restriction" and c.citation
    }
    assert cites == {TRANSACTION_PROHIBITION.section}
    assert TRANSACTION_RESTRICTIONS.section not in cites


def test_stepien_is_answered_per_pick_not_once_for_the_team():
    """
    The Clippers hold firsts in 2027, 2029, 2031 and 2033 with 2028, 2030 and
    2032 bare. Trading any held first creates a consecutive bare pair, so every
    one of them is untradeable -- while the position itself is legal.
    """
    state = second_apron_uncapped()
    state.picks = forfeited_firsts("LAC")
    report = team_trade_constraints(state, as_of=WHEN)
    stepien = detail_for(report, "stepien")
    assert "may not trade its 2027, 2029, 2031, 2033 first-round pick" in stepien
    assert "may trade its first-round pick in" not in stepien
    assert "forfeited in 2029, 2030, 2031, 2032, 2033" in detail_for(report, "forfeited_picks")


def test_a_team_with_spare_firsts_is_told_which_it_may_trade():
    from engine.fixtures.picks import own_outright
    from engine.picks import PickInventory

    inv = PickInventory(team_id="FIX")
    for year in (2027, 2028, 2029, 2030):
        inv.picks.append(own_outright("FIX", year))
    state = room_team()
    state.picks = inv
    report = team_trade_constraints(state, as_of=WHEN)
    # With four consecutive firsts held, moving any one leaves no bare pair.
    assert "may trade its first-round pick in 2027, 2028, 2029, 2030" in detail_for(
        report, "stepien"
    )


def test_an_unloaded_pick_inventory_says_so_rather_than_reporting_no_limits():
    report = team_trade_constraints(room_team(), as_of=WHEN)
    assert "not loaded" in detail_for(report, "picks")


def test_a_team_at_the_roster_minimum_must_take_back_what_it_sends():
    state = room_team()
    state.roster = RosterState(standard_count=STANDARD_MIN)
    report = team_trade_constraints(state, as_of=WHEN)
    assert "at least as many players as it sends" in detail_for(report, "roster_minimum")


def test_a_team_above_the_minimum_is_told_how_many_it_may_shed():
    state = room_team()
    state.roster = RosterState(standard_count=STANDARD_MIN + 2)
    report = team_trade_constraints(state, as_of=WHEN)
    assert "may send up to 2 more player(s)" in detail_for(report, "roster_minimum")


def test_a_full_roster_must_send_as_many_as_it_takes():
    state = room_team()
    state.roster = RosterState(standard_count=STANDARD_MAX)
    report = team_trade_constraints(state, as_of=WHEN)
    assert "send out at least" in detail_for(report, "roster_maximum")


def test_capacity_answers_the_question_in_dollars():
    """
    A list of prohibitions is not the whole answer. "How much can I take back
    for him" is the number the question is really after.
    """
    state = capped_below_ceiling()
    player = state.contracts[0].player_id
    report = team_trade_constraints(state, player_id=player, as_of=WHEN, base_season_cap=BASE_CAP)
    capacity = detail_for(report, "take_back_capacity")
    assert "permits taking back up to $" in capacity


def test_capacity_is_omitted_rather_than_guessed_without_the_base_cap():
    """The Expanded formula needs the 2023-24 cap; absent it, say nothing."""
    state = capped_below_ceiling()
    report = team_trade_constraints(state, player_id=state.contracts[0].player_id, as_of=WHEN)
    assert "take_back_capacity" not in kinds(report)


def test_an_unknown_no_trade_clause_is_surfaced_not_assumed_absent():
    """
    Unknown and absent are different answers, and only one of them is safe to
    stay quiet about. An unverifiable clause has to be said out loud, because a
    clause the team does not know about can still veto the deal.
    """
    from engine.fixtures.contracts import trade_kicker_unknown

    state = room_team()
    contract = trade_kicker_unknown(SEASON_2026_27)
    state.contracts.append(contract)
    report = team_trade_constraints(state, player_id=contract.player_id, as_of=WHEN)
    assert "unknown_no_trade_clause" in kinds(report)
    assert any(a.field_name == "no_trade_clause" for a in report.assumptions)


def test_a_clause_known_to_be_absent_is_not_reported_as_a_constraint():
    """The counterpart: a filler contract has no clause, so there is nothing to say."""
    state = room_team()
    player = state.contracts[0].player_id
    assert state.contracts[0].no_trade_clause.is_absent
    report = team_trade_constraints(state, player_id=player, as_of=WHEN)
    assert "unknown_no_trade_clause" not in kinds(report)
    assert "no_trade_clause" not in kinds(report)


def test_a_missing_signing_date_blocks_the_window_check_loudly():
    """
    A trade-date bar that is not evaluated reads as "tradeable", so the gap has
    to be stated rather than passed over.
    """
    state = room_team()
    report = team_trade_constraints(state, player_id=state.contracts[0].player_id, as_of=WHEN)
    assert "cannot be checked" in detail_for(report, "trade_window")
    assert any(a.field_name == "signed_date" for a in report.assumptions)


def test_naming_no_player_omits_the_player_level_constraints():
    """A team-level question must not invent a subject."""
    report = team_trade_constraints(second_apron_uncapped(), as_of=WHEN)
    for kind in ("take_back_capacity", "unknown_no_trade_clause", "trade_window"):
        assert kind not in kinds(report)


def test_every_restriction_row_has_a_description():
    """A row with no phrase would render as an empty prohibition."""
    for row in RestrictionRow:
        assert row.describe().strip()
        assert not row.describe().startswith("may not")  # the caller adds that


@pytest.mark.parametrize("shell", [room_team, capped_below_ceiling, second_apron_uncapped])
def test_a_report_always_states_its_apron_position(shell):
    report = team_trade_constraints(shell(), as_of=WHEN)
    assert report.describe().startswith(report.team_id)
    assert "apron" in report.describe() or "tax" in report.describe()
