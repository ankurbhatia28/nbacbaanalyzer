"""
What an apron team may and may not do (tasks 3.6, 3.7).

**There is no list.** Every summary presents "first apron restrictions" and
"second apron restrictions" as enumerated prohibitions -- cannot aggregate,
cannot send cash, cannot use the taxpayer MLE, and so on. The CBA contains no
such enumeration. The restrictions are *emergent* from one sentence,
Art. VII 2(e)(2)(i)(A), p. 211:

    A Team may not engage in a transaction set forth in the Transaction
    Restrictions Table if, immediately following such transaction, the Team's
    Apron Team Salary for such Salary Cap Year would exceed the "Applicable
    Apron Level" that corresponds with such transaction in the table.

A team already above the second apron cannot aggregate salaries because
aggregation is row H, whose Applicable Apron Level is the second apron, and it
would exceed that level immediately after. The prohibition is not stated; it
falls out. The same sentence produces every other item on the familiar lists.

This matters beyond tidiness. A hand-written list is a transcription that can be
stale or incomplete; deriving from 2(e)(2)(i)(A) means any row added to the table
is automatically enforced, and the engine can explain *why* a team is barred
rather than asserting that it is.

Two further conditions sit alongside:

  2(e)(2)(i)(B)  having engaged, the team may not exceed that level for the
                 remainder of the Salary Cap Year -- the ceiling, already
                 modelled in `apron.CeilingSet`
  6(n)(1)        several exceptions are available only to a team at or above
                 the cap, or below it by less than the exception amount
  6(m)           exceptions may not be combined to sign or acquire at a higher
                 salary than any single one permits -- universal, not apron-specific
"""

from __future__ import annotations

from dataclasses import dataclass

from .apron import ApronLevel, RestrictionRow, SeasonThresholds
from .citations import (
    TRANSACTION_PROHIBITION,
    TRANSACTION_RESTRICTIONS_TABLE,
    Citation,
)
from .season import Season

TRANSITION_CARVE_OUT_SEASON = "2023-2024"
"""
Art. VII 2(e)(5): rows F-J executed during 2023-24 create no 2023-24 ceiling --
and, per the document's own Example 5, are exempt from the 2(e)(2)(i)(A)
prohibition as well. Team E's Apron Team Salary of $175m exceeded the $170m
first apron and the trade was still permitted, "notwithstanding" that fact.
"""


@dataclass(frozen=True, slots=True)
class TransactionPermission:
    row: RestrictionRow
    permitted: bool
    applicable_level: ApronLevel
    level_amount: int
    salary_after: int
    exempt: bool = False
    citation: Citation = TRANSACTION_PROHIBITION

    def describe(self) -> str:
        verb = "may" if self.permitted else "may not"
        if self.exempt:
            return (
                f"{verb} use row {self.row.value}: exempt for {TRANSITION_CARVE_OUT_SEASON} "
                f"under Art. VII 2(e)(5) despite salary of ${self.salary_after:,}"
            )
        return (
            f"{verb} use row {self.row.value}: would leave Apron Team Salary at "
            f"${self.salary_after:,} against a {self.applicable_level.value.replace('_', ' ')} "
            f"of ${self.level_amount:,}"
        )


def may_engage(
    row: RestrictionRow, *, apron_salary_after: int, season: Season
) -> TransactionPermission:
    """
    Art. VII 2(e)(2)(i)(A). The forward-looking half of the rule: a team may not
    engage in a listed transaction if it would be over that row's level
    immediately afterwards.

    Distinct from 2(e)(2)(i)(B), which is what happens *after* a permitted
    transaction. Implementing only (B) leaves a team able to do things it may
    not do in the first place.
    """
    thresholds = SeasonThresholds(season.first_apron, season.second_apron)
    level = row.applicable_apron
    amount = thresholds.amount_for(level)

    # 2(e)(5): rows F-J in 2023-24 are exempt. The document's Example 5 applies
    # this to the (i)(A) prohibition, not only to the (i)(B) ceiling -- Team E
    # was permitted "notwithstanding" being over the level.
    exempt = season.season_id == TRANSITION_CARVE_OUT_SEASON and "F" <= row.value <= "J"
    return TransactionPermission(
        row=row,
        permitted=exempt or apron_salary_after <= amount,
        applicable_level=level,
        level_amount=amount,
        salary_after=apron_salary_after,
        exempt=exempt,
    )


def available_transactions(
    *, apron_salary: int, season: Season, salary_added: int = 0
) -> list[TransactionPermission]:
    """
    Which rows a team may use, given where its salary would land.

    `salary_added` is what the contemplated transaction would add. Zero answers
    "what could this team do at all?", which is the shape task 3.19 wants.
    """
    after = apron_salary + salary_added
    return [
        may_engage(row, apron_salary_after=after, season=season)
        for row in RestrictionRow
        if row.is_reachable_after_2024
    ]


def barred_transactions(
    *, apron_salary: int, season: Season, salary_added: int = 0
) -> list[TransactionPermission]:
    """The familiar 'apron restrictions', derived rather than transcribed."""
    return [
        p
        for p in available_transactions(
            apron_salary=apron_salary, season=season, salary_added=salary_added
        )
        if not p.permitted
    ]


def exception_requires_being_near_the_cap(
    *, team_salary_excluding_exceptions: int, exception_amount: int, season: Season
) -> bool:
    """
    Art. VII 6(n)(1). The Disabled Player, Bi-annual, both Mid-Level and Traded
    Player Exceptions are available only if the team is at or above the cap, or
    below it by less than the exception amount.

    A team with real room uses its room instead -- which is why 6(j)(1)(v) and
    6(j)(2) are carved out of this condition.
    """
    if team_salary_excluding_exceptions >= season.salary_cap:
        return True
    room = season.salary_cap - team_salary_excluding_exceptions
    return room < exception_amount


NON_AGGREGATION_RULE = (
    "Art. VII 6(m): other than as Section 6(j) allows, exceptions may not be "
    "combined to sign or acquire players at salaries greater than any single "
    "exception permits. A team holding several may choose which to use."
)
"""6(m) applies to every team regardless of apron status -- often described as an
apron restriction, which it is not."""


def explain_apron_position(*, apron_salary: int, season: Season) -> str:
    """A sentence naming what a team cannot do and why, for task 3.19."""
    barred = barred_transactions(apron_salary=apron_salary, season=season)
    if not barred:
        return "no Transaction Restrictions Table row is closed to this team"
    first = [p.row.value for p in barred if p.applicable_level is ApronLevel.FIRST]
    second = [p.row.value for p in barred if p.applicable_level is ApronLevel.SECOND]
    parts = []
    if first:
        parts.append(f"rows {', '.join(first)} (first apron)")
    if second:
        parts.append(f"rows {', '.join(second)} (second apron)")
    return (
        f"Apron Team Salary of ${apron_salary:,} closes {' and '.join(parts)} — "
        f"not by a stated prohibition but because {TRANSACTION_RESTRICTIONS_TABLE.short} "
        "rows may not be used when the team would exceed their level afterwards"
    )
