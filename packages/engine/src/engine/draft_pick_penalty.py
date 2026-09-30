"""
The frozen first-round pick, Article VII Section 2(f), pp. 219-220.

The second-apron consequence that is not a Transaction Restrictions Table row,
and therefore does not fall out of 2(e)(2)(i)(A) like the others. It has to be
implemented separately.

"Second Apron Team" is a *snapshot*, not a season-long condition: a team whose
Apron Team Salary exceeds the second apron **as of the start of its last Regular
Season game** in that Salary Cap Year. A team over the line all winter that dips
under before its final game is not one.

Being a Second Apron Team for a Salary Cap Year does three things:

  freeze     its first-round pick in the first Draft after the seventh Season
             following that one may not be traded, conditionally or otherwise
  penalty    if it is a Second Apron Team in two or more of the next four Salary
             Cap Years, that pick becomes the **final** selection of the first
             round
  release    if fewer than two, the pick becomes tradeable again the day after
             the Regular Season of the third of those four years in which it was
             not a Second Apron Team

The CBA's own worked example anchors the arithmetic: a Second Apron Team in
2024-25 cannot trade its **2032** first.
"""

from __future__ import annotations

from dataclasses import dataclass

from .citations import DRAFT_PICK_PENALTY, Citation

SEASONS_AHEAD = 7
"""2(f)(2)(i): "the seventh Season that follows the Season occurring within such
Salary Cap Year", then the first Draft after it."""

LOOKAHEAD_YEARS = 4
"""2(f)(2)(ii): the four Salary Cap Years immediately following."""

PENALTY_THRESHOLD = 2
"""2(f)(2)(ii)(A): a Second Apron Team in two or more of those four."""

COMPLIANT_YEARS_TO_RELEASE = 3
"""2(f)(2)(ii)(B): released after the third of the four in which it was not one."""

FIRST_APPLICABLE_SALARY_CAP_YEAR = 2024
"""2(f)(2): "Beginning with the 2024-25 Salary Cap Year"."""


def frozen_draft_year(salary_cap_year_start: int) -> int:
    """
    The Draft whose first-round pick freezes, for a team that is a Second Apron
    Team in the Salary Cap Year beginning in `salary_cap_year_start`.

    2024-25 -> 2032, per the CBA's own example. Seven Seasons follow the Season
    in that Salary Cap Year, and the pick is in the first Draft after those.
    """
    return salary_cap_year_start + SEASONS_AHEAD + 1


@dataclass(frozen=True, slots=True)
class PickPenaltyStatus:
    draft_year: int
    frozen: bool
    penalised: bool
    released_after_salary_cap_year: int | None
    second_apron_years: tuple[int, ...]
    resolved: bool = True
    """
    False while the four-year window is still running. Until it closes the pick
    is frozen and the outcome is genuinely unknown -- a team in 2026 cannot say
    whether its 2032 pick will be penalised, because 2027 and 2028 have not
    happened. Reporting a provisional answer as settled would be a guess.
    """
    citation: Citation = DRAFT_PICK_PENALTY

    def describe(self) -> str:
        if self.penalised:
            return (
                f"the {self.draft_year} first-round pick may not be traded and will be the "
                f"final selection of the first round"
            )
        # An unresolved pick is also frozen, so this must be checked first or
        # the frozen branch swallows it and reports a settled answer.
        if not self.resolved:
            return (
                f"the {self.draft_year} first-round pick may not be traded; whether it is "
                "also penalised is not yet determined"
            )
        if self.frozen:
            return f"the {self.draft_year} first-round pick may not be traded"
        if self.released_after_salary_cap_year is not None:
            return (
                f"the {self.draft_year} first-round pick became tradeable after the "
                f"{self.released_after_salary_cap_year}-"
                f"{str(self.released_after_salary_cap_year + 1)[2:]} Regular Season"
            )
        return f"the {self.draft_year} first-round pick is unaffected"


def evaluate(
    *,
    trigger_salary_cap_year: int,
    second_apron_in: set[int],
    known_through_salary_cap_year: int | None = None,
) -> PickPenaltyStatus:
    """
    Resolve a frozen pick, given which Salary Cap Years the team finished as a
    Second Apron Team. Years are the starting calendar year, so 2024 means
    2024-25.

    `second_apron_in` should contain the trigger year itself plus any of the
    following four in which the team finished over the line.

    `known_through_salary_cap_year` is the last year whose outcome is actually
    known. Omitting it asserts the whole window is settled; passing a year
    inside the window leaves the status unresolved, which is the honest answer
    while seasons are still to be played.
    """
    draft_year = frozen_draft_year(trigger_salary_cap_year)
    if trigger_salary_cap_year < FIRST_APPLICABLE_SALARY_CAP_YEAR:
        return PickPenaltyStatus(draft_year, False, False, None, ())
    if trigger_salary_cap_year not in second_apron_in:
        return PickPenaltyStatus(draft_year, False, False, None, ())

    window = [trigger_salary_cap_year + n for n in range(1, LOOKAHEAD_YEARS + 1)]
    over = tuple(y for y in window if y in second_apron_in)

    if len(over) >= PENALTY_THRESHOLD:
        return PickPenaltyStatus(draft_year, True, True, None, over)

    known_through = known_through_salary_cap_year
    if known_through is not None and known_through < window[-1]:
        # The window is still running, so the outcome cannot be stated.
        return PickPenaltyStatus(draft_year, True, False, None, over, resolved=False)

    compliant = [y for y in window if y not in second_apron_in]
    released = (
        compliant[COMPLIANT_YEARS_TO_RELEASE - 1]
        if len(compliant) >= COMPLIANT_YEARS_TO_RELEASE
        else None
    )
    return PickPenaltyStatus(draft_year, released is None, False, released, over)


def penalised_pick_order(teams_by_winning_percentage: list[tuple[str, float]]) -> list[str]:
    """
    2(f)(1)(ii): when several penalised picks land in one Draft, those teams
    select in **inverse order of winning percentage** — the better record picks
    last, at the very end of the round.
    """
    return [team for team, _ in sorted(teams_by_winning_percentage, key=lambda t: t[1])]
