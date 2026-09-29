"""
When a player may be traded (task 3.13), Article VII Section 8(c)-(d), pp. 284-286.

Four separate rules, each with its own clock:

  8(c)      no trade after the deadline in what could be the contract's last
            Season -- including a Season made last by an Option or ETO
  8(d)(i)   draft rookies and two-way signings: 30 days from signing
  8(d)(ii)  free agent signings: later of 3 months or December 15
  8(d)(iii) re-signed with his prior team on a raise above 120%: later of
            3 months or January 15

8(d)(iii) blocks the **trade**, not merely aggregation. The separate two-month
aggregation bar is Art. VII 6(j)(4)(i) and is a different rule with a different
clock -- conflating them under-restricts trades that are outright barred.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from .citations import TRADE_RULES, Citation

ROOKIE_AND_TWO_WAY_DAYS = 30
"""8(d)(i)"""

FREE_AGENT_MONTHS = 3
RE_SIGNED_MONTHS = 3
FREE_AGENT_GATE = (12, 15)
"""8(d)(ii): December 15 of the Salary Cap Year the contract was signed."""

RE_SIGNED_GATE = (1, 15)
"""8(d)(iii): January 15."""

RE_SIGNED_RAISE_THRESHOLD = 1.20
"""8(d)(iii): first-season Salary greater than 120% of the prior contract's last."""


class TradeBarReason(StrEnum):
    ROOKIE_OR_TWO_WAY = "rookie_or_two_way_30_days"
    FREE_AGENT_SIGNING = "free_agent_signing"
    RE_SIGNED_WITH_RAISE = "re_signed_with_raise"
    FINAL_SEASON_DEADLINE_PASSED = "final_season_deadline_passed"


@dataclass(frozen=True, slots=True)
class TradeEligibility:
    tradeable: bool
    reason: TradeBarReason | None = None
    eligible_from: date | None = None
    citation: Citation = TRADE_RULES
    detail: str | None = None


def _plus_months(start: date, months: int) -> date:
    month = start.month - 1 + months
    year = start.year + month // 12
    month = month % 12 + 1
    day = min(
        start.day,
        [
            31,
            29 if year % 4 == 0 and (year % 100 or year % 400 == 0) else 28,
            31,
            30,
            31,
            30,
            31,
            31,
            30,
            31,
            30,
            31,
        ][month - 1],
    )
    return date(year, month, day)


def _gate(signed: date, gate: tuple[int, int]) -> date:
    """
    The December 15 / January 15 date of the Salary Cap Year the contract was
    signed. A Salary Cap Year runs July 1 to June 30, so a January gate for a
    contract signed in the autumn falls in the *following* calendar year.
    """
    month, day = gate
    year = signed.year if month >= 7 else signed.year + (1 if signed.month >= 7 else 0)
    return date(year, month, day)


def free_agent_eligible_from(signed: date) -> date:
    """8(d)(ii): the later of three months or December 15."""
    return max(_plus_months(signed, FREE_AGENT_MONTHS), _gate(signed, FREE_AGENT_GATE))


def re_signed_eligible_from(signed: date) -> date:
    """8(d)(iii): the later of three months or January 15."""
    return max(_plus_months(signed, RE_SIGNED_MONTHS), _gate(signed, RE_SIGNED_GATE))


def rookie_eligible_from(signed: date) -> date:
    """8(d)(i): thirty days."""
    from datetime import timedelta

    return signed + timedelta(days=ROOKIE_AND_TWO_WAY_DAYS)


def re_signed_restriction_applies(
    *,
    team_over_cap_after_signing: bool,
    is_qualifying_or_early_qualifying_veteran: bool,
    new_first_season_salary: int,
    prior_last_season_salary: int,
    is_minimum_contract_without_bonuses: bool,
) -> bool:
    """
    8(d)(iii) applies only when every condition holds, and never to a minimum
    contract with no bonuses. All four are required -- a raise alone is not enough.
    """
    if is_minimum_contract_without_bonuses:
        return False
    if not (team_over_cap_after_signing and is_qualifying_or_early_qualifying_veteran):
        return False
    return new_first_season_salary > RE_SIGNED_RAISE_THRESHOLD * prior_last_season_salary


def check(
    *,
    when: date,
    signed: date,
    is_rookie_or_two_way: bool = False,
    is_free_agent_signing: bool = False,
    re_signed_with_raise: bool = False,
    signed_as_part_of_sign_and_trade: bool = False,
) -> TradeEligibility:
    """
    Whether a contract may be traded on `when`.

    Sign-and-trade contracts are exempt on the initial trade; the bar applies if
    the contract is traded a second time (8(d)(ii)).
    """
    if re_signed_with_raise:
        eligible = re_signed_eligible_from(signed)
        if when < eligible:
            return TradeEligibility(
                False,
                TradeBarReason.RE_SIGNED_WITH_RAISE,
                eligible,
                detail="re-signed with his prior team above 120%; barred until the later "
                "of three months or January 15",
            )
    if is_free_agent_signing and not signed_as_part_of_sign_and_trade:
        eligible = free_agent_eligible_from(signed)
        if when < eligible:
            return TradeEligibility(
                False,
                TradeBarReason.FREE_AGENT_SIGNING,
                eligible,
                detail="signed as a free agent; barred until the later of three months "
                "or December 15",
            )
    if is_rookie_or_two_way:
        eligible = rookie_eligible_from(signed)
        if when < eligible:
            return TradeEligibility(
                False,
                TradeBarReason.ROOKIE_OR_TWO_WAY,
                eligible,
                detail="barred for thirty days following signing",
            )
    return TradeEligibility(True)
