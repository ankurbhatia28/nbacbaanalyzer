"""
Salary matching (task 3.4), transcribed from Article VII, Section 6(j).

The commonly cited "125% plus $100,000" is the **2017** CBA and is wrong for
this agreement. Under the 2023 CBA the standard band is *stricter* -- 100% plus
$250,000 -- and the flexibility moved into a separate Expanded exception whose
price is a first-apron ceiling for the rest of the Salary Cap Year.

Encoding the familiar number would have made every matching verdict wrong, and
plausibly so. That is precisely the failure ADR-001 exists to prevent, which is
why 3.1 requires reading the document rather than a summary.

Worked example, Milwaukee's July 2026 acquisition of Caris LeVert:

    out $7,631,722 (Harris + Prince), in $14,809,200 -- 194% of outgoing
    Standard allows  $7,881,722  -> not enough
    Expanded allows $15,513,444  -> fits

So the trade required the Expanded exception, which is row E of the Transaction
Restrictions Table, which sets a first-apron ceiling. The engine reaches that
conclusion from the text, independent of any tracker.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .citations import (
    TPE_AGGREGATED,
    TPE_ALLOWANCE_REMOVED_AT_APRON,
    TPE_EXPANDED,
    TPE_ROOM,
    TPE_STANDARD,
    TPE_TRANSITION,
    Citation,
)
from .season import Season

ALLOWANCE = 250_000
"""Art. VII 6(j)(1): the flat allowance added to every matching band."""

TRANSITION_SEASON = "2023-2024"
"""Art. VII 6(j)(1)(iii): the Transition exception exists for this season only."""

EXPANDED_BASE_CAP_SEASON = "2023-2024"
EXPANDED_BASE_AMOUNT = 7_500_000
"""Art. VII 6(j)(1)(iv)(y)(B): $7.5m scaled by the cap's growth since 2023-24."""


class MatchingExceptionKind(StrEnum):
    STANDARD = "standard"
    AGGREGATED = "aggregated"
    TRANSITION = "transition"
    EXPANDED = "expanded"
    ROOM = "room"


CITATION_FOR: dict[MatchingExceptionKind, Citation] = {
    MatchingExceptionKind.STANDARD: TPE_STANDARD,
    MatchingExceptionKind.AGGREGATED: TPE_AGGREGATED,
    MatchingExceptionKind.TRANSITION: TPE_TRANSITION,
    MatchingExceptionKind.EXPANDED: TPE_EXPANDED,
    MatchingExceptionKind.ROOM: TPE_ROOM,
}


@dataclass(frozen=True, slots=True)
class Allowance:
    """The most incoming salary one exception permits, and why."""

    kind: MatchingExceptionKind
    amount: int
    citation: Citation
    allowance_applied: int
    note: str | None = None

    def permits(self, incoming: int) -> bool:
        return incoming <= self.amount


def allowance_cushion(post_assignment_apron_salary: int, season: Season) -> int:
    """
    Art. VII 6(j)(3): the $250,000 allowance drops to $0 when a team's
    post-assignment Apron Team Salary would exceed the First Apron Level.

    Easy to miss, and it is the difference between legal and illegal in exactly
    the trades that matter -- the ones squeezing against a threshold.
    """
    return 0 if post_assignment_apron_salary > season.first_apron else ALLOWANCE


def standard(outgoing: int, season: Season, post_apron_salary: int) -> Allowance:
    """6(j)(1)(i): 100% of the traded player's pre-trade salary, plus the allowance."""
    cushion = allowance_cushion(post_apron_salary, season)
    return Allowance(
        MatchingExceptionKind.STANDARD,
        outgoing + cushion,
        TPE_STANDARD,
        cushion,
        None if cushion else f"allowance removed: {TPE_ALLOWANCE_REMOVED_AT_APRON.short}",
    )


def aggregated(outgoing: int, season: Season, post_apron_salary: int) -> Allowance:
    """6(j)(1)(ii): 100% of the aggregated salaries, plus the allowance."""
    cushion = allowance_cushion(post_apron_salary, season)
    return Allowance(
        MatchingExceptionKind.AGGREGATED,
        outgoing + cushion,
        TPE_AGGREGATED,
        cushion,
        None if cushion else f"allowance removed: {TPE_ALLOWANCE_REMOVED_AT_APRON.short}",
    )


def transition(outgoing: int, season: Season, post_apron_salary: int) -> Allowance | None:
    """6(j)(1)(iii): 110% plus the allowance -- 2023-24 only. None in any other season."""
    if season.season_id != TRANSITION_SEASON:
        return None
    cushion = allowance_cushion(post_apron_salary, season)
    return Allowance(
        MatchingExceptionKind.TRANSITION,
        int(1.10 * outgoing) + cushion,
        TPE_TRANSITION,
        cushion,
        "available in 2023-24 only",
    )


def expanded(
    outgoing: int, season: Season, post_apron_salary: int, base_season_cap: int
) -> Allowance:
    """
    6(j)(1)(iv): the greater of

        (y) the lesser of  (A) 200% + allowance
                           (B) 100% + $7.5m scaled by cap growth since 2023-24
        (z) 125% + allowance

    The nested greater-of-lesser-of is the actual text, not a simplification.
    """
    cushion = allowance_cushion(post_apron_salary, season)
    a = int(2.00 * outgoing) + cushion
    b = outgoing + int(EXPANDED_BASE_AMOUNT * season.salary_cap / base_season_cap)
    z = int(1.25 * outgoing) + cushion
    amount = max(min(a, b), z)
    return Allowance(
        MatchingExceptionKind.EXPANDED,
        amount,
        TPE_EXPANDED,
        cushion,
        f"(y)=min({a:,}, {b:,}) vs (z)={z:,}",
    )


def room(cap_room: int, season: Season, post_apron_salary: int) -> Allowance:
    """
    6(j)(1)(v): a team under the cap may absorb its room plus the allowance --
    and may not combine this with any of (i)-(iv) in the same trade.
    """
    cushion = allowance_cushion(post_apron_salary, season)
    return Allowance(
        MatchingExceptionKind.ROOM,
        cap_room + cushion,
        TPE_ROOM,
        cushion,
        "may not be combined with 6(j)(1)(i)-(iv) in the same trade",
    )


def best_allowance(
    outgoing: int,
    incoming: int,
    season: Season,
    post_apron_salary: int,
    base_season_cap: int,
    *,
    aggregating: bool,
    cap_room: int | None = None,
) -> Allowance | None:
    """
    The least-consequential exception that permits `incoming`, or None.

    Ordered deliberately: Standard and Room carry no apron ceiling, while
    Aggregated and Expanded are rows H and E of the Transaction Restrictions
    Table. A team should not be told it triggered a ceiling it did not need.
    """
    candidates: list[Allowance] = []
    if cap_room is not None and cap_room > 0:
        candidates.append(room(cap_room, season, post_apron_salary))
    if not aggregating:
        candidates.append(standard(outgoing, season, post_apron_salary))
    else:
        candidates.append(aggregated(outgoing, season, post_apron_salary))
    trans = transition(outgoing, season, post_apron_salary)
    if trans is not None:
        candidates.append(trans)
    candidates.append(expanded(outgoing, season, post_apron_salary, base_season_cap))

    for candidate in candidates:
        if candidate.permits(incoming):
            return candidate
    return None
