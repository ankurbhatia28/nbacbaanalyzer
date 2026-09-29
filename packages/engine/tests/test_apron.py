"""
Apron status vs apron ceiling, and ceilings as a set.

Both modelling rules came from real 2026-27 situations, so the tests use them.
"""

from datetime import date

import pytest

from engine import ApronLevel, ApronStatus, CeilingSet, HardCapCeiling, RestrictionRow
from engine.apron import SeasonThresholds, classify

CAP, TAX, A1, A2 = 166_000_000, 201_690_000, 210_690_000, 223_690_000
TH = SeasonThresholds(A1, A2)


@pytest.mark.parametrize(
    "salary,expected",
    [
        (160_324_651, ApronStatus.ROOM),  # Brooklyn
        (194_157_318, ApronStatus.OVER_CAP),  # Houston
        (208_710_566, ApronStatus.TAXPAYER),  # Denver, committed only
        (215_000_000, ApronStatus.FIRST_APRON),
        (232_001_714, ApronStatus.SECOND_APRON),  # Oklahoma City
    ],
)
def test_classify(salary, expected):
    assert classify(salary, CAP, TAX, A1, A2) is expected


def test_all_eleven_restriction_rows_map_to_an_apron():
    first = [r for r in RestrictionRow if r.applicable_apron is ApronLevel.FIRST]
    second = [r for r in RestrictionRow if r.applicable_apron is ApronLevel.SECOND]
    assert [r.value for r in first] == list("ABCDEFG")
    assert [r.value for r in second] == list("HIJK")


def test_paying_cash_sets_a_second_apron_ceiling():
    # Row I. Easy to assume this is a first-apron trigger; it is not.
    assert RestrictionRow.I_CASH_PAID.applicable_apron is ApronLevel.SECOND


def test_taxpayer_mle_sets_a_second_apron_ceiling():
    assert RestrictionRow.K_TAXPAYER_MLE.applicable_apron is ApronLevel.SECOND


def test_expanded_tpe_sets_a_first_apron_ceiling():
    assert RestrictionRow.E_EXPANDED_TPE.applicable_apron is ApronLevel.FIRST


def test_post_season_rows_bind_the_following_year():
    # Sec. 2(e)(2)(ii) applies to rows E-J only.
    assert RestrictionRow.E_EXPANDED_TPE.binds_subsequent_year_if_post_season
    assert RestrictionRow.I_CASH_PAID.binds_subsequent_year_if_post_season
    assert not RestrictionRow.A_BI_ANNUAL.binds_subsequent_year_if_post_season
    assert not RestrictionRow.K_TAXPAYER_MLE.binds_subsequent_year_if_post_season


def test_milwaukee_holds_two_ceilings_and_the_lower_binds():
    """
    Milwaukee paid cash on Jun 24 (row I -> second apron) and acquired Caris
    LeVert with an Expanded TPE on Jul 8 (row E -> first apron). Trackers show
    "1st Apron" because the lower ceiling governs.
    """
    ceilings = CeilingSet()
    ceilings.add(
        HardCapCeiling(
            RestrictionRow.I_CASH_PAID,
            ApronLevel.SECOND,
            date(2026, 6, 24),
            "2026-2027",
            "cash to ORL",
        )
    )
    ceilings.add(
        HardCapCeiling(
            RestrictionRow.E_EXPANDED_TPE,
            ApronLevel.FIRST,
            date(2026, 7, 8),
            "2026-2027",
            "Caris LeVert",
        )
    )
    level, amount = ceilings.effective(TH)
    assert level is ApronLevel.FIRST
    assert amount == A1
    assert len(ceilings) == 2  # both retained, not collapsed


def test_no_ceiling_is_not_the_same_as_a_high_one():
    assert CeilingSet().effective(TH) is None


def test_status_and_ceiling_are_independent():
    """
    Houston sits below the second apron but may not cross it. Oklahoma City sits
    above it with no ceiling at all. A single field cannot express both.
    """
    houston = CeilingSet()
    houston.add(
        HardCapCeiling(
            RestrictionRow.K_TAXPAYER_MLE,
            ApronLevel.SECOND,
            date(2026, 7, 10),
            "2026-2027",
            "Marcus Smart",
        )
    )
    assert classify(194_157_318, CAP, TAX, A1, A2) is ApronStatus.OVER_CAP
    assert houston.effective(TH) == (ApronLevel.SECOND, A2)

    okc = CeilingSet()
    assert classify(232_001_714, CAP, TAX, A1, A2) is ApronStatus.SECOND_APRON
    assert okc.effective(TH) is None


def test_row_g_is_unreachable_for_seasons_we_model():
    """
    Its apron level is transcribed correctly, but the Transition exception it
    refers to existed in 2023-24 only, and Sec. 2(e)(5) exempts rows F-J executed
    during 2023-24 from creating a 2023-24 ceiling. So the one season row G can
    fire in is the season it is exempted in.
    """
    assert RestrictionRow.G_TRANSITION_TPE.applicable_apron is ApronLevel.FIRST
    assert not RestrictionRow.G_TRANSITION_TPE.is_reachable_after_2024
    assert all(
        row.is_reachable_after_2024
        for row in RestrictionRow
        if row is not RestrictionRow.G_TRANSITION_TPE
    )


def test_the_transition_exception_is_unavailable_outside_2023_24():
    """The reason row G cannot fire: the exception itself does not exist."""
    from dataclasses import replace

    from engine.fixtures import SEASON_2026_27
    from engine.salary_matching import transition

    assert transition(10_000_000, SEASON_2026_27, 150_000_000) is None
    assert transition(10_000_000, replace(SEASON_2026_27, season_id="2023-2024"), 150_000_000)
