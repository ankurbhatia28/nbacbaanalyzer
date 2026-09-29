"""
Maximum Annual Salary, Article II Section 7(a).

Encodes the three errors summaries make: treating the first tier as 1-6 rather
than "fewer than seven", treating the higher maximum as available to a whole
tier rather than a subset, and dropping the 105%-of-prior-salary alternative.
"""

import pytest

from engine.max_salary import MaxTier, maximum_annual_salary, tier_for

CAP = 166_000_000


@pytest.mark.parametrize(
    "yos,expected",
    [
        (0, MaxTier.UNDER_SEVEN),  # "fewer than seven" includes a rookie
        (6, MaxTier.UNDER_SEVEN),
        (7, MaxTier.SEVEN_TO_NINE),
        (9, MaxTier.SEVEN_TO_NINE),
        (10, MaxTier.TEN_PLUS),
        (18, MaxTier.TEN_PLUS),
    ],
)
def test_tier_boundaries(yos, expected):
    assert tier_for(yos) is expected


def test_the_first_tier_starts_at_zero_not_one():
    """Commonly written as "1 to 6 years"; the text says "fewer than seven"."""
    assert tier_for(0) is MaxTier.UNDER_SEVEN


def test_standard_percentages_by_tier():
    assert maximum_annual_salary(years_of_service=3, salary_cap=CAP).percentage == 0.25
    assert maximum_annual_salary(years_of_service=8, salary_cap=CAP).percentage == 0.30
    assert maximum_annual_salary(years_of_service=11, salary_cap=CAP).percentage == 0.35


def test_a_ten_plus_player_has_no_higher_tier():
    got = maximum_annual_salary(years_of_service=12, salary_cap=CAP, meets_higher_max_criteria=True)
    assert got.percentage == 0.35
    assert not got.higher_max_applied
    assert "top tier" in (got.note or "")


def test_thirty_percent_requires_fifth_year_eligibility_not_just_the_tier():
    """Meeting the criteria is not sufficient; the tier's own gate also applies."""
    criteria_only = maximum_annual_salary(
        years_of_service=4, salary_cap=CAP, meets_higher_max_criteria=True
    )
    assert criteria_only.percentage == 0.25
    assert not criteria_only.higher_max_applied

    eligible = maximum_annual_salary(
        years_of_service=4,
        salary_cap=CAP,
        meets_higher_max_criteria=True,
        is_fifth_year_eligible=True,
    )
    assert eligible.percentage == 0.30
    assert eligible.higher_max_applied


def test_thirty_five_percent_requires_eight_or_nine_years_and_tenure():
    seven = maximum_annual_salary(
        years_of_service=7,
        salary_cap=CAP,
        meets_higher_max_criteria=True,
        has_designated_veteran_tenure=True,
    )
    assert seven.percentage == 0.30  # in the tier, outside the 8-9 window
    assert "outside the 8-9" in (seven.note or "")

    no_tenure = maximum_annual_salary(
        years_of_service=9, salary_cap=CAP, meets_higher_max_criteria=True
    )
    assert no_tenure.percentage == 0.30

    both = maximum_annual_salary(
        years_of_service=9,
        salary_cap=CAP,
        meets_higher_max_criteria=True,
        has_designated_veteran_tenure=True,
    )
    assert both.percentage == 0.35
    assert both.higher_max_applied


def test_the_105_percent_alternative_can_exceed_the_percentage():
    """
    Every tier is "the greater of X% or 105% of the prior final-season salary".
    Dropping the alternative understates the maximum for anyone on a large deal.
    """
    got = maximum_annual_salary(
        years_of_service=12, salary_cap=CAP, prior_final_season_salary=60_000_000
    )
    assert got.amount == 63_000_000
    assert got.used_prior_salary_floor

    smaller = maximum_annual_salary(
        years_of_service=12, salary_cap=CAP, prior_final_season_salary=10_000_000
    )
    assert smaller.amount == int(0.35 * CAP)
    assert not smaller.used_prior_salary_floor


def test_every_result_carries_the_higher_max_citation():
    got = maximum_annual_salary(years_of_service=5, salary_cap=CAP)
    assert got.citation.article == "II"
    assert got.citation.section == "7"
