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

from collections.abc import Iterator
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


# ----------------------------------------------------------------------
# Structuring a trade across several exceptions
# ----------------------------------------------------------------------

MAX_PARTITIONED_PLAYERS = 8
"""
Above this, enumerating partitions costs more than it is worth. Bell(8) is 4,140
and Bell(12) is over four million; real trades rarely send more than a handful
of players from one team.
"""


def _partitions(items: list[int]) -> Iterator[list[list[int]]]:
    """Every way of splitting a list into non-empty groups."""
    if not items:
        yield []
        return
    first, rest = items[0], items[1:]
    for smaller in _partitions(rest):
        for i, group in enumerate(smaller):
            yield smaller[:i] + [[first, *group]] + smaller[i + 1 :]
        yield [[first], *smaller]


def _group_allowance(
    group: list[int], season: Season, post_apron_salary: int, base_season_cap: int
) -> int:
    """The most a single exception permits against one group of traded players."""
    total = sum(group)
    options = [
        standard(total, season, post_apron_salary).amount
        if len(group) == 1
        else aggregated(total, season, post_apron_salary).amount,
        expanded(total, season, post_apron_salary, base_season_cap).amount,
    ]
    return max(options)


@dataclass(frozen=True, slots=True)
class Structure:
    """How a trade is split across exceptions, and what that permits in total."""

    total_allowance: int
    groups: tuple[tuple[int, ...], ...]
    citation: Citation = TPE_STANDARD

    def permits(self, incoming: int) -> bool:
        return incoming <= self.total_allowance

    @property
    def exception_count(self) -> int:
        return len(self.groups)


def best_structure(
    outgoing_salaries: list[int],
    season: Season,
    post_apron_salary: int,
    base_season_cap: int,
) -> Structure:
    """
    The most incoming salary a team may absorb, allowing it to split its outgoing
    players across several exceptions.

    Art. VII 6(j)(1)(i) lets one exception "replace one (1) Traded Player", so a
    team sending several players may use several exceptions -- and 6(m) permits
    exactly that, carving Section 6(j) out of its general bar on combining
    exceptions.

    Treating a trade as a single exception understates capacity, sometimes
    badly. Sending four players separately earns the $250,000 allowance four
    times rather than once; aggregating them instead opens the Expanded
    formula against a larger base. Which wins depends on the salaries, so both
    are considered.
    """
    salaries = [s for s in outgoing_salaries if s > 0]
    if not salaries:
        return Structure(0, ())
    if len(salaries) > MAX_PARTITIONED_PLAYERS:
        # Fall back to the two obvious structures rather than enumerate.
        singles = sum(
            _group_allowance([s], season, post_apron_salary, base_season_cap) for s in salaries
        )
        whole = _group_allowance(salaries, season, post_apron_salary, base_season_cap)
        if singles >= whole:
            return Structure(singles, tuple((s,) for s in salaries))
        return Structure(whole, (tuple(salaries),))

    best_total = -1
    best_groups: tuple[tuple[int, ...], ...] = ()
    for partition in _partitions(salaries):
        total = sum(
            _group_allowance(group, season, post_apron_salary, base_season_cap)
            for group in partition
        )
        if total > best_total:
            best_total = total
            best_groups = tuple(tuple(g) for g in partition)
    return Structure(best_total, best_groups)
