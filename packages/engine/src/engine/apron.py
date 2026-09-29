"""
Apron status, and the ceilings a team's own transactions impose on it.

Two distinct concepts that are routinely conflated, and conflating them produces
opposite answers (tasks 1.15 and 1.16):

  * **Status** -- where a team's Apron Team Salary currently sits.
  * **Ceiling** -- what a past transaction forbids it from exceeding.

Houston sits far *below* the second apron yet may not cross it, having signed a
player with the Taxpayer MLE. Oklahoma City sits far *above* it and may go
higher. One field cannot express both.

The CBA never uses the phrase "hard cap" -- zero occurrences in 676 pages. The
mechanism is Article VII, Section 2(e)(2)(i)(B): a team that engages in a
transaction listed in the Transaction Restrictions Table (Section 2(e)(4),
pp. 214-215) may not, for the remainder of the Salary Cap Year, have an Apron
Team Salary exceeding that row's Applicable Apron Level.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class ApronLevel(StrEnum):
    FIRST = "first_apron"
    SECOND = "second_apron"


class ApronStatus(StrEnum):
    """Where a team's Apron Team Salary sits. Not a ceiling."""

    ROOM = "room"  # below the cap
    OVER_CAP = "over_cap"  # above cap, below tax
    TAXPAYER = "taxpayer"  # above tax, below first apron
    FIRST_APRON = "first_apron"  # above first apron, below second
    SECOND_APRON = "second_apron"  # above second apron


class RestrictionRow(StrEnum):
    """
    Transaction Restrictions Table, Art. VII Sec. 2(e)(4), rows A-K.

    Rows A-G set a ceiling at the First Apron Level; H-K at the Second.
    """

    A_BI_ANNUAL = "A"  # signs or acquires using the Bi-annual Exception
    B_NON_TAXPAYER_MLE = "B"  # signs or acquires using the Non-Taxpayer MLE
    C_SIGN_AND_TRADE_IN = "C"  # acquires a player on a Sec. 8(e)(1) contract
    D_WAIVED_PLAYER_ABOVE_MLE = "D"  # in-season signing of a waived player paid above the MLE
    E_EXPANDED_TPE = "E"  # acquires using an Expanded Traded Player Exception
    F_POST_SEASON_STANDARD_TPE = "F"  # standard TPE used after its Regular Season
    G_TRANSITION_TPE = "G"  # acquires using a Transition Traded Player Exception
    H_AGGREGATED_TPE = "H"  # acquires using an Aggregated Standard TPE
    I_CASH_PAID = "I"  # pays cash to another team in a trade
    J_TPE_FROM_SIGN_AND_TRADE = "J"  # TPE arising from a signed-and-traded contract
    K_TAXPAYER_MLE = "K"  # signs using the Taxpayer MLE

    @property
    def applicable_apron(self) -> ApronLevel:
        return ApronLevel.FIRST if self.value <= "G" else ApronLevel.SECOND

    @property
    def binds_subsequent_year_if_post_season(self) -> bool:
        """
        Sec. 2(e)(2)(ii): rows E-J executed after the Regular Season restrict the
        *following* Salary Cap Year rather than the current one.
        """
        return "E" <= self.value <= "J"


class SeasonThresholds:
    """Minimal view of a Season needed to price an apron level."""

    def __init__(self, first_apron: int, second_apron: int) -> None:
        self.first_apron = first_apron
        self.second_apron = second_apron

    def amount_for(self, level: ApronLevel) -> int:
        return self.first_apron if level is ApronLevel.FIRST else self.second_apron


@dataclass(frozen=True, slots=True)
class HardCapCeiling:
    """One ceiling, created by one transaction."""

    row: RestrictionRow
    level: ApronLevel
    effective_date: date
    season_id: str
    source_transaction: str | None = None

    def describe(self) -> str:
        where = f" ({self.source_transaction})" if self.source_transaction else ""
        return f"{self.level.value} via row {self.row.value}{where}"


@dataclass
class CeilingSet:
    """
    All ceilings a team holds for a season. The lowest binds.

    Milwaukee is the worked example: a first-apron ceiling from acquiring Caris
    LeVert with an Expanded TPE on Jul 8, and a second-apron ceiling from paying
    cash on Jun 24. Trackers show "1st Apron" because the lower one governs --
    which is why this cannot be a single field.
    """

    ceilings: list[HardCapCeiling] = field(default_factory=list)

    def add(self, ceiling: HardCapCeiling) -> None:
        self.ceilings.append(ceiling)

    def effective(self, season: SeasonThresholds) -> tuple[ApronLevel, int] | None:
        """The binding ceiling and its dollar amount, or None if unrestricted."""
        if not self.ceilings:
            return None
        best = min(self.ceilings, key=lambda c: season.amount_for(c.level))
        return best.level, season.amount_for(best.level)

    def binding(self) -> HardCapCeiling | None:
        if not self.ceilings:
            return None
        # FIRST sorts before SECOND, and first apron is always the lower dollar figure
        return min(self.ceilings, key=lambda c: 0 if c.level is ApronLevel.FIRST else 1)

    def __len__(self) -> int:
        return len(self.ceilings)


def classify(apron_team_salary: int, cap: int, tax: int, apron1: int, apron2: int) -> ApronStatus:
    """Where a team's Apron Team Salary sits. Says nothing about ceilings."""
    if apron_team_salary < cap:
        return ApronStatus.ROOM
    if apron_team_salary < tax:
        return ApronStatus.OVER_CAP
    if apron_team_salary < apron1:
        return ApronStatus.TAXPAYER
    if apron_team_salary < apron2:
        return ApronStatus.FIRST_APRON
    return ApronStatus.SECOND_APRON
