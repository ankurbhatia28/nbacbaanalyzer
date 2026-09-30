"""
Apron restrictions, derived rather than transcribed.

The CBA contains no list of "second apron restrictions". Every familiar item
falls out of Art. VII 2(e)(2)(i)(A): a team may not engage in a Transaction
Restrictions Table row if it would exceed that row's level immediately after.

These tests assert the derivation reproduces the familiar lists, which is the
check that matters -- if it diverges, either the derivation is wrong or the
popular account is.
"""

import pytest

from engine.apron import ApronLevel, RestrictionRow
from engine.apron_restrictions import (
    available_transactions,
    barred_transactions,
    exception_requires_being_near_the_cap,
    explain_apron_position,
    may_engage,
)
from engine.fixtures import SEASON_2026_27 as S

ROOM, TAXPAYER = 160_000_000, 205_000_000
FIRST_APRON, SECOND_APRON = 215_000_000, 232_000_000


def barred_rows(salary: int) -> set[str]:
    return {p.row.value for p in barred_transactions(apron_salary=salary, season=S)}


def test_a_team_below_both_aprons_is_barred_from_nothing():
    assert barred_rows(ROOM) == set()
    assert barred_rows(TAXPAYER) == set()


def test_a_first_apron_team_loses_the_first_apron_rows():
    """Bi-annual, non-taxpayer MLE, sign-and-trade acquisition, waived-player
    signing above the MLE, expanded TPE, post-season standard TPE."""
    assert barred_rows(FIRST_APRON) == set("ABCDEF")


def test_a_second_apron_team_loses_everything_reachable():
    assert barred_rows(SECOND_APRON) == set("ABCDEF") | set("HIJK")


def test_the_famous_second_apron_restrictions_are_exactly_rows_h_to_k():
    """
    "Cannot aggregate salaries" is row H. "Cannot send cash" is row I. "Cannot
    use the taxpayer MLE" is row K. None is stated as a prohibition anywhere.
    """
    barred = {
        p.row
        for p in barred_transactions(apron_salary=SECOND_APRON, season=S)
        if p.applicable_level is ApronLevel.SECOND
    }
    assert barred == {
        RestrictionRow.H_AGGREGATED_TPE,  # cannot aggregate salaries
        RestrictionRow.I_CASH_PAID,  # cannot send cash in a trade
        RestrictionRow.J_TPE_FROM_SIGN_AND_TRADE,
        RestrictionRow.K_TAXPAYER_MLE,  # cannot use the taxpayer MLE
    }


def test_a_taxpayer_team_may_still_aggregate():
    """Below the second apron, so row H remains open -- the distinction the
    popular account collapses when it says "apron teams cannot aggregate"."""
    got = may_engage(RestrictionRow.H_AGGREGATED_TPE, apron_salary_after=TAXPAYER, season=S)
    assert got.permitted


def test_the_test_is_the_salary_after_not_before():
    """2(e)(2)(i)(A) measures immediately following the transaction."""
    just_under = may_engage(
        RestrictionRow.K_TAXPAYER_MLE, apron_salary_after=S.second_apron, season=S
    )
    just_over = may_engage(
        RestrictionRow.K_TAXPAYER_MLE, apron_salary_after=S.second_apron + 1, season=S
    )
    assert just_under.permitted
    assert not just_over.permitted


def test_adding_salary_can_close_a_row_that_was_open():
    open_now = [
        p.row for p in available_transactions(apron_salary=205_000_000, season=S) if p.permitted
    ]
    after = [
        p.row
        for p in available_transactions(apron_salary=205_000_000, season=S, salary_added=20_000_000)
        if p.permitted
    ]
    assert len(after) < len(open_now)


def test_the_unreachable_row_is_excluded_from_the_derivation():
    rows = {p.row for p in available_transactions(apron_salary=ROOM, season=S)}
    assert RestrictionRow.G_TRANSITION_TPE not in rows


def test_the_explanation_says_why_not_merely_that():
    text = explain_apron_position(apron_salary=SECOND_APRON, season=S)
    assert "not by a stated prohibition" in text
    assert "rows H, I, J, K" in text


def test_a_team_with_room_is_unrestricted_and_says_so():
    assert "closed to this team" in explain_apron_position(apron_salary=ROOM, season=S)


@pytest.mark.parametrize(
    "team_salary,exception,expected",
    [
        (S.salary_cap + 1, 10_000_000, True),  # over the cap
        (S.salary_cap, 10_000_000, True),  # exactly at it
        (S.salary_cap - 5_000_000, 10_000_000, True),  # room smaller than the exception
        (S.salary_cap - 50_000_000, 10_000_000, False),  # real room; use it instead
    ],
)
def test_exception_availability_under_6n1(team_salary, exception, expected):
    assert (
        exception_requires_being_near_the_cap(
            team_salary_excluding_exceptions=team_salary, exception_amount=exception, season=S
        )
        is expected
    )
