"""The fixture libraries must reproduce the real situations they mirror."""

from dataclasses import replace

import pytest

from engine import ApronLevel, ApronStatus
from engine.fixtures import (
    ALL_CONTRACT_FIXTURES,
    ALL_SHELLS,
    SEASON_2026_27,
    capped_below_ceiling,
    forfeited_firsts,
    holds_divergence,
    minimum_deal,
    over_38_contract,
    pick_poverty,
    range_protected,
    room_team,
    second_apron_uncapped,
    trade_kicker_unknown,
)
from engine.fixtures.contracts import OVER_38_BIRTH_YEAR
from engine.fixtures.picks import BARE_FIRST_ROUND_YEARS


def test_every_shell_builds():
    for shell in ALL_SHELLS:
        state = shell()
        assert state.committed_salary() > 0, shell.__name__


def test_houston_and_okc_are_inverses():
    """
    The case that forced status and ceiling apart: one is below the second
    apron but barred from crossing it, the other is above it and unrestricted.
    """
    hou, okc = capped_below_ceiling(), second_apron_uncapped()

    assert hou.apron_status() is not ApronStatus.SECOND_APRON
    assert hou.effective_ceiling() == (ApronLevel.SECOND.value, SEASON_2026_27.second_apron)
    assert hou.room_below_ceiling() > 0  # below its ceiling

    assert okc.apron_status() is ApronStatus.SECOND_APRON
    assert okc.effective_ceiling() is None  # no ceiling at all


def test_denver_shell_crosses_only_once_holds_count():
    den = holds_divergence()
    assert den.committed_salary() < SEASON_2026_27.second_apron
    assert den.cap_salary() > SEASON_2026_27.second_apron


def test_brooklyn_shell_shows_the_room_gap():
    """Under the cap on committed salary, over it once holds count."""
    bkn = room_team()
    assert bkn.committed_salary() < SEASON_2026_27.salary_cap
    assert bkn.cap_salary() > SEASON_2026_27.salary_cap


def test_milwaukee_shell_keeps_both_ceilings():
    from engine.fixtures import first_apron_capped

    mil = first_apron_capped()
    assert len(mil.ceilings) == 2
    assert mil.effective_ceiling() == (ApronLevel.FIRST.value, SEASON_2026_27.first_apron)


def test_clippers_own_firsts_are_forfeited_2029_to_2033():
    inv = forfeited_firsts()
    gone = sorted(p.year for p in inv.picks if p.forfeited)
    assert gone == [2029, 2030, 2031, 2032, 2033]


def test_clippers_are_not_pickless_in_the_penalty_years():
    """
    The penalty took their own firsts, but they still hold other teams' picks in
    2029, 2031 and 2033. Modelling five straight empty years would make a legal
    position look illegal under Stepien.
    """
    inv = forfeited_firsts()
    bare = [y for y in range(2027, 2034) if not inv.has_first_in(y)]
    assert bare == list(BARE_FIRST_ROUND_YEARS) == [2028, 2030, 2032]
    assert not any(y + 1 in bare for y in bare), "bare years must not be consecutive"


def test_a_pick_conveyed_away_does_not_count_as_held():
    """Ownership, not origin. LAC originated the 2028 first; Boston holds it."""
    inv = forfeited_firsts()
    assert any(p.year == 2028 and p.current_owner_team_id == "BOS" for p in inv.firsts_in(2028))
    assert not inv.has_first_in(2028)


def test_pick_poverty_shell_carries_the_inventory():
    assert pick_poverty().picks is not None


def test_protected_pick_conveys_outside_its_range():
    pick = range_protected()
    assert not pick.conveys_at(3)  # inside 1-4
    assert pick.conveys_at(9)  # outside


def test_fixtures_follow_the_season_rather_than_hardcoding_dollars():
    """
    Boundary fixtures must move with the cap, or they silently stop testing
    boundaries the moment league figures change.
    """
    bigger = replace(SEASON_2026_27, minimum_scale={5: 9_999_999})
    assert minimum_deal(SEASON_2026_27).years[0].cap_figure != 9_999_999
    assert minimum_deal(bigger).years[0].cap_figure == 9_999_999


def test_fixture_seasons_are_consecutive_from_the_given_season():
    later = replace(SEASON_2026_27, season_id="2030-2031")
    ids = [y.season_id for y in over_38_contract(later).years]
    assert ids == ["2030-2031", "2031-2032", "2032-2033", "2033-2034"]


def test_over_38_fixture_actually_triggers_the_rule():
    c = over_38_contract(SEASON_2026_27)
    assert c.season_count >= 4
    assert c.triggers_over_38_rule(OVER_38_BIRTH_YEAR) is True


def test_unknown_kicker_fixture_stays_unknown():
    c = trade_kicker_unknown(SEASON_2026_27)
    assert c.trade_kicker_pct.is_unknown
    with pytest.raises(TypeError):
        bool(c.trade_kicker_pct)


def test_all_contract_fixtures_build():
    for fn in ALL_CONTRACT_FIXTURES:
        c = fn(SEASON_2026_27)
        assert c.years, fn.__name__
