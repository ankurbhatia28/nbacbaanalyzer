"""
The CBA's own worked examples, Art. VII §2(e), pp. 216-219 (task 3.22).

The document states five scenarios with explicit figures and tells you the
outcome. They are free, authoritative test cases -- the closest thing to a
reference implementation this domain has, written by the people who drafted the
rule. Every one of them should pass without argument.

The examples use their own assumed apron levels rather than real ones, stated in
the document immediately above them.
"""

from dataclasses import replace

import pytest

from engine.apron import ApronLevel, RestrictionRow
from engine.apron_restrictions import may_engage
from engine.fixtures import SEASON_2026_27

# "Assume the following First Apron Levels and Second Apron Levels" -- p. 216
ASSUMED = {
    "2023-2024": (170_000_000, 180_500_000),
    "2024-2025": (178_500_000, 189_500_000),
    "2025-2026": (187_500_000, 199_000_000),
}


def season(season_id: str):
    first, second = ASSUMED[season_id]
    return replace(SEASON_2026_27, season_id=season_id, first_apron=first, second_apron=second)


def test_example_1_team_a_non_taxpayer_mle_is_permitted():
    """
    Team A signs using the Non-Taxpayer MLE (row B). Apron Team Salary
    immediately following is $165m against a $170m first apron, so the signing
    is "not prohibited by Section 2(e)(2)(i)(A)".
    """
    got = may_engage(
        RestrictionRow.B_NON_TAXPAYER_MLE,
        apron_salary_after=165_000_000,
        season=season("2023-2024"),
    )
    assert got.permitted
    assert got.applicable_level is ApronLevel.FIRST
    assert got.level_amount == 170_000_000


def test_example_2_team_b_post_season_standard_tpe_is_permitted():
    """
    Team B uses a Standard TPE after the Regular Season in which it arose
    (row F). 2024-25 Apron Team Salary is $177m against a $178.5m first apron.
    """
    got = may_engage(
        RestrictionRow.F_POST_SEASON_STANDARD_TPE,
        apron_salary_after=177_000_000,
        season=season("2024-2025"),
    )
    assert got.permitted


def test_example_3_team_c_taxpayer_mle_is_permitted():
    """
    Team C signs using the Taxpayer MLE (row K, second apron). 2025-26 Apron
    Team Salary immediately following is $195m against a $199m second apron.
    """
    got = may_engage(
        RestrictionRow.K_TAXPAYER_MLE,
        apron_salary_after=195_000_000,
        season=season("2025-2026"),
    )
    assert got.permitted
    assert got.applicable_level is ApronLevel.SECOND


def test_example_4_team_d_aggregation_is_prohibited():
    """
    The only example with a negative outcome, stated in the document: the trade
    "is prohibited by Section 2(e)(2)(i)(A) above because, immediately following
    the trade, Team D's 2024-25 Apron Team Salary would exceed $189.5 million".
    """
    got = may_engage(
        RestrictionRow.H_AGGREGATED_TPE,
        apron_salary_after=195_000_000,
        season=season("2024-2025"),
    )
    assert not got.permitted
    assert got.applicable_level is ApronLevel.SECOND
    assert got.level_amount == 189_500_000


def test_example_5_transition_tpe_is_permitted_despite_exceeding_the_apron():
    """
    The subtlest one, and the reason it earns its place: Team E's Apron Team
    Salary of $175m *exceeds* the $170m first apron, and the trade is still
    permitted -- "notwithstanding" that fact -- because §2(e)(5) exempts rows
    F-J executed during 2023-24.

    Without §2(e)(5) the engine prohibits this, which is exactly what it did
    before this example was encoded.
    """
    s = season("2023-2024")
    got = may_engage(RestrictionRow.G_TRANSITION_TPE, apron_salary_after=175_000_000, season=s)
    assert got.permitted
    assert got.exempt
    assert got.salary_after > got.level_amount  # over the line, still allowed


def test_the_carve_out_does_not_reach_rows_outside_f_through_j():
    """§2(e)(5) names rows F through J. Row B at the same salary is prohibited."""
    s = season("2023-2024")
    assert not may_engage(
        RestrictionRow.B_NON_TAXPAYER_MLE, apron_salary_after=175_000_000, season=s
    ).permitted


@pytest.mark.parametrize("season_id", list(ASSUMED))
def test_the_carve_out_is_confined_to_2023_24(season_id):
    s = season(season_id)
    got = may_engage(RestrictionRow.H_AGGREGATED_TPE, apron_salary_after=10**9, season=s)
    assert got.exempt is (season_id == "2023-2024")
