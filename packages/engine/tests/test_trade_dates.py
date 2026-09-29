"""Trade date calendar, Article VII Section 8(c)-(d)."""

from datetime import date

import pytest

from engine.trade_dates import (
    TradeBarReason,
    check,
    free_agent_eligible_from,
    re_signed_eligible_from,
    re_signed_restriction_applies,
    rookie_eligible_from,
)


def test_free_agent_bar_is_the_later_of_three_months_or_december_15():
    # Signed in July: three months lands in October, so December 15 governs.
    assert free_agent_eligible_from(date(2026, 7, 10)) == date(2026, 12, 15)
    # Signed in October: three months lands past December 15, so that governs.
    assert free_agent_eligible_from(date(2026, 10, 20)) == date(2027, 1, 20)


def test_re_signed_bar_is_the_later_of_three_months_or_january_15():
    assert re_signed_eligible_from(date(2026, 7, 6)) == date(2027, 1, 15)
    assert re_signed_eligible_from(date(2026, 11, 1)) == date(2027, 2, 1)


def test_january_gate_falls_in_the_following_calendar_year():
    """A Salary Cap Year runs July to June, so January is the next calendar year."""
    assert re_signed_eligible_from(date(2026, 7, 6)).year == 2027


def test_rookie_and_two_way_bar_is_thirty_days():
    assert rookie_eligible_from(date(2026, 7, 10)) == date(2026, 8, 9)


def test_a_free_agent_signing_is_barred_before_december_15():
    got = check(when=date(2026, 11, 1), signed=date(2026, 7, 10), is_free_agent_signing=True)
    assert not got.tradeable
    assert got.reason is TradeBarReason.FREE_AGENT_SIGNING
    assert got.eligible_from == date(2026, 12, 15)


def test_the_same_signing_is_tradeable_afterwards():
    assert check(
        when=date(2026, 12, 16), signed=date(2026, 7, 10), is_free_agent_signing=True
    ).tradeable


def test_a_sign_and_trade_is_exempt_on_the_initial_trade():
    """8(d)(ii): the bar applies if the contract is traded a second time."""
    assert check(
        when=date(2026, 7, 11),
        signed=date(2026, 7, 10),
        is_free_agent_signing=True,
        signed_as_part_of_sign_and_trade=True,
    ).tradeable


@pytest.mark.parametrize(
    "kwargs,expected",
    [
        (
            dict(
                team_over_cap_after_signing=True,
                is_qualifying_or_early_qualifying_veteran=True,
                new_first_season_salary=121,
                prior_last_season_salary=100,
                is_minimum_contract_without_bonuses=False,
            ),
            True,
        ),
        # exactly 120% is not "greater than" 120%
        (
            dict(
                team_over_cap_after_signing=True,
                is_qualifying_or_early_qualifying_veteran=True,
                new_first_season_salary=120,
                prior_last_season_salary=100,
                is_minimum_contract_without_bonuses=False,
            ),
            False,
        ),
        # a minimum contract with no bonuses is carved out entirely
        (
            dict(
                team_over_cap_after_signing=True,
                is_qualifying_or_early_qualifying_veteran=True,
                new_first_season_salary=500,
                prior_last_season_salary=100,
                is_minimum_contract_without_bonuses=True,
            ),
            False,
        ),
        # the team must be over the cap after signing
        (
            dict(
                team_over_cap_after_signing=False,
                is_qualifying_or_early_qualifying_veteran=True,
                new_first_season_salary=200,
                prior_last_season_salary=100,
                is_minimum_contract_without_bonuses=False,
            ),
            False,
        ),
        # and the player must be a qualifying or early qualifying veteran
        (
            dict(
                team_over_cap_after_signing=True,
                is_qualifying_or_early_qualifying_veteran=False,
                new_first_season_salary=200,
                prior_last_season_salary=100,
                is_minimum_contract_without_bonuses=False,
            ),
            False,
        ),
    ],
)
def test_re_signed_restriction_needs_every_condition(kwargs, expected):
    """A raise alone is not enough -- all four conditions must hold."""
    assert re_signed_restriction_applies(**kwargs) is expected


def test_the_re_signed_bar_blocks_the_trade_not_merely_aggregation():
    """
    8(d)(iii) is a trade bar. The two-month aggregation bar is the separate
    6(j)(4)(i), with a different clock. Conflating them under-restricts a player
    who cannot be traded at all.
    """
    got = check(when=date(2026, 10, 1), signed=date(2026, 7, 6), re_signed_with_raise=True)
    assert not got.tradeable
    assert got.reason is TradeBarReason.RE_SIGNED_WITH_RAISE
