"""
The two "poison pill" rules (task 3.11).

"Poison pill" is a nickname and appears nowhere in the CBA. It describes two
distinct provisions that share one mechanism -- a salary *deemed* to equal the
average of a contract's remaining years, for one party's Room calculation only:

  Art. VII 8(g)      Rookie Extension Trade Rule, pp. 288-289
  Art. XI 5(d)       Gilbert Arenas provision, pp. 346-347

The asymmetry is the point. In both, one team's cap treatment uses the actual
year-by-year figures while the other's uses the average, so a contract that is
comfortable for one side is prohibitive for the other. An engine that values a
contract identically for both teams gets these backwards.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .citations import (
    ARENAS_DEEMED_AVERAGE,
    ARENAS_OFFER_SHEET_LIMIT,
    ARENAS_THIRD_YEAR,
    ROOKIE_EXTENSION_TRADE_RULE,
    Citation,
)

CAP_GROWTH_ASSUMPTION = 1.045
"""
Art. VII 8(g)(i)-(ii): when the extended term is expressed as a percentage of
the cap, assume the cap in the first extended year equals 104.5% of the cap at
the time of the proposed trade.
"""

ARENAS_FOURTH_YEAR_MOVEMENT = 0.045
"""Art. XI 5(d)(ii)(A): the fourth year may move by at most 4.5% of the third."""


class Party(StrEnum):
    """Which side of the transaction a valuation is for."""

    ACQUIRING = "acquiring"
    OUTGOING = "outgoing"


@dataclass(frozen=True, slots=True)
class DeemedSalary:
    amount: int
    deemed: bool
    citation: Citation | None
    explanation: str


def rookie_extension_trade_value(
    *,
    final_original_year_salary: int,
    extended_term_salaries: list[int],
    traded_before_extension_takes_effect: bool,
    party: Party,
) -> DeemedSalary:
    """
    Art. VII 8(g). A rookie-scale contract extended under 7(b) and traded before
    the first day of the next Salary Cap Year is valued, **only for the acquiring
    team's Room**, at the average of the final original year and every extended
    year. The outgoing team uses the actual figure.
    """
    if not traded_before_extension_takes_effect:
        return DeemedSalary(
            final_original_year_salary,
            False,
            None,
            "extension already in effect; the deeming rule no longer applies",
        )
    if party is Party.OUTGOING:
        return DeemedSalary(
            final_original_year_salary,
            False,
            ROOKIE_EXTENSION_TRADE_RULE,
            "the rule applies only to the acquiring team's Room; the outgoing team "
            "uses the actual salary",
        )
    years = [final_original_year_salary, *extended_term_salaries]
    average = sum(years) // len(years)
    return DeemedSalary(
        average,
        True,
        ROOKIE_EXTENSION_TRADE_RULE,
        f"deemed the average of {len(years)} years "
        f"(${final_original_year_salary:,} plus the extended term)",
    )


def assumed_cap_for_extended_term(cap_at_trade: int) -> int:
    """Art. VII 8(g)(i)(a): 104.5% of the cap in effect when the trade would occur."""
    return int(CAP_GROWTH_ASSUMPTION * cap_at_trade)


def arenas_applies(years_of_service: int) -> bool:
    """Art. XI 5(d): restricted free agents with one or two Years of Service."""
    return years_of_service in (1, 2)


def arenas_first_year_limit(non_taxpayer_mle: int) -> int:
    """
    Art. XI 5(d)(i): first-year Salary plus Unlikely Bonuses may not exceed the
    Non-Taxpayer MLE -- which is what forces the third-year balloon that makes
    the provision bite.
    """
    return non_taxpayer_mle


def arenas_offer_sheet_room_value(offer_sheet_salaries: list[int]) -> DeemedSalary:
    """
    Art. XI 5(d)(iii): for the **offering** team's Room, the first year is deemed
    the average across every year of the Offer Sheet.

    The incumbent team matching the sheet carries the actual year-by-year
    figures, which spike in the third year. That gap is the poison.
    """
    if not offer_sheet_salaries:
        raise ValueError("an offer sheet must cover at least one Salary Cap Year")
    average = sum(offer_sheet_salaries) // len(offer_sheet_salaries)
    return DeemedSalary(
        average,
        True,
        ARENAS_DEEMED_AVERAGE,
        f"deemed the average of {len(offer_sheet_salaries)} years for the offering "
        f"team's Room; a matching team carries the actual figures",
    )


def arenas_fourth_year_bounds(third_year_salary: int) -> tuple[int, int]:
    """Art. XI 5(d)(ii)(A): the fourth year may move by at most 4.5% of the third."""
    delta = int(ARENAS_FOURTH_YEAR_MOVEMENT * third_year_salary)
    return third_year_salary - delta, third_year_salary + delta


ARENAS_BALLOON_CONDITIONS: tuple[tuple[str, Citation], ...] = (
    ("the Offer Sheet may contain no bonuses of any kind", ARENAS_THIRD_YEAR),
    (
        "100% of Base Compensation in each Season must be protected for lack of skill "
        "and injury or illness, with no individually-negotiated limitations",
        ARENAS_THIRD_YEAR,
    ),
    (
        "the first two Salary Cap Years must be at the maximum permitted by 5(d)(i)",
        ARENAS_OFFER_SHEET_LIMIT,
    ),
)
"""Art. XI 5(d)(ii)(A)-(C): all required before the third-year balloon is available."""
