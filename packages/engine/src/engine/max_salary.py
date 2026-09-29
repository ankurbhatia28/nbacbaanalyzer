"""
Maximum Annual Salary, Article II Section 7(a), pp. 59-61.

Three tiers by Years of Service, each expressed as "the greater of X% of the
Salary Cap or 105% of the final-season salary of the prior Contract". The 105%
alternative is easy to drop when summarising and changes the answer for anyone
coming off a large deal.

Two of the tiers carry a *higher* maximum for a narrow subset -- not for the
whole tier, which is the other thing summaries routinely flatten:

  fewer than 7 YOS   25%, or 30% for "5th Year Eligible Players" only
  7 to 9 YOS         30%, or 35% for 8-9 YOS with continuous-team tenure
  10 or more YOS     35%, no higher tier

Both higher maxima require the Higher Max Criteria (All-NBA, Defensive Player
of the Year, or MVP -- never All-Star), but measure them at different moments.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .citations import HIGHER_MAX_CRITERIA, Citation

STANDARD_UNDER_7 = 0.25
STANDARD_7_TO_9 = 0.30
STANDARD_10_PLUS = 0.35

HIGHER_FIFTH_YEAR = 0.30
"""Art. II 7(a)(i): 5th Year Eligible Players only, not the whole tier."""

HIGHER_DESIGNATED_VETERAN = 0.35
"""Art. II 7(a)(ii): 8-9 YOS with the tenure condition only."""

PRIOR_SALARY_MULTIPLIER = 1.05
"""Every tier: "the greater of X% ... or 105% of the final Season's Salary"."""


class MaxTier(StrEnum):
    UNDER_SEVEN = "under_seven"
    SEVEN_TO_NINE = "seven_to_nine"
    TEN_PLUS = "ten_plus"


def tier_for(years_of_service: int) -> MaxTier:
    """Art. II 7(a)(i)-(iii). Note the first tier is *fewer than seven*, so 0 is in it."""
    if years_of_service < 7:
        return MaxTier.UNDER_SEVEN
    if years_of_service < 10:
        return MaxTier.SEVEN_TO_NINE
    return MaxTier.TEN_PLUS


@dataclass(frozen=True, slots=True)
class MaximumSalary:
    amount: int
    percentage: float
    tier: MaxTier
    used_prior_salary_floor: bool
    higher_max_applied: bool
    citation: Citation
    note: str | None = None


def standard_percentage(tier: MaxTier) -> float:
    return {
        MaxTier.UNDER_SEVEN: STANDARD_UNDER_7,
        MaxTier.SEVEN_TO_NINE: STANDARD_7_TO_9,
        MaxTier.TEN_PLUS: STANDARD_10_PLUS,
    }[tier]


def maximum_annual_salary(
    *,
    years_of_service: int,
    salary_cap: int,
    prior_final_season_salary: int | None = None,
    meets_higher_max_criteria: bool = False,
    is_fifth_year_eligible: bool = False,
    has_designated_veteran_tenure: bool = False,
) -> MaximumSalary:
    """
    The most a contract's first Season may provide, before incentives.

    `is_fifth_year_eligible` and `has_designated_veteran_tenure` are separate
    from years of service on purpose: meeting the Higher Max Criteria is not
    enough on its own, and treating the tier as sufficient is the common error.
    """
    tier = tier_for(years_of_service)
    percentage = standard_percentage(tier)
    higher = False
    note: str | None = None

    if meets_higher_max_criteria:
        if tier is MaxTier.UNDER_SEVEN and is_fifth_year_eligible:
            percentage, higher = HIGHER_FIFTH_YEAR, True
            note = "5th Year Eligible Player, criteria met as of the July 1 after year four"
        elif tier is MaxTier.SEVEN_TO_NINE and has_designated_veteran_tenure:
            if years_of_service in (8, 9):
                percentage, higher = HIGHER_DESIGNATED_VETERAN, True
                note = "Designated Veteran Player Contract, criteria met at execution"
            else:
                note = "seven years of service is outside the 8-9 designated veteran window"
        elif tier is MaxTier.TEN_PLUS:
            note = "already at the top tier; no higher maximum exists"
        else:
            note = "Higher Max Criteria met but the tier's eligibility condition is not"

    by_percentage = int(percentage * salary_cap)
    floor = (
        int(PRIOR_SALARY_MULTIPLIER * prior_final_season_salary) if prior_final_season_salary else 0
    )
    amount = max(by_percentage, floor)

    return MaximumSalary(
        amount=amount,
        percentage=percentage,
        tier=tier,
        used_prior_salary_floor=floor > by_percentage,
        higher_max_applied=higher,
        citation=HIGHER_MAX_CRITERIA,
        note=note,
    )
