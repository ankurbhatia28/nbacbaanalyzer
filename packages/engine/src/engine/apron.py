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
    # Row G is dead in practice, and the table alone does not show it: the
    # Transition exception exists in 2023-24 only (6(j)(1)(iii)), and 2(e)(5)
    # exempts rows F-J executed during 2023-24 from creating a 2023-24 ceiling.
    # The one season it can fire is the season it is exempted in. The only
    # residue is 2(e)(2)(ii): used after the 2023-24 Regular Season but before
    # 30 June 2024, it could bind 2024-25. Never reachable for seasons we model.
    G_TRANSITION_TPE = "G"  # acquires using a Transition Traded Player Exception
    H_AGGREGATED_TPE = "H"  # acquires using an Aggregated Standard TPE
    I_CASH_PAID = "I"  # pays cash to another team in a trade
    J_TPE_FROM_SIGN_AND_TRADE = "J"  # TPE arising from a signed-and-traded contract
    K_TAXPAYER_MLE = "K"  # signs using the Taxpayer MLE

    def describe(self) -> str:
        """
        The row as a phrase completing "may not ...".

        Taken from the Table's own wording rather than the familiar shorthand:
        row H is "aggregate" in every summary written about the second apron,
        but what it actually covers is acquiring a player using an exception
        created by aggregating contracts, which is a narrower thing.
        """
        return _ROW_DESCRIPTIONS[self]

    @property
    def applicable_apron(self) -> ApronLevel:
        return ApronLevel.FIRST if self.value <= "G" else ApronLevel.SECOND

    @property
    def is_reachable_after_2024(self) -> bool:
        """
        False for row G only. See the note on G_TRANSITION_TPE: the exception it
        refers to expired after 2023-24, so no later season can trigger it.
        """
        return self is not RestrictionRow.G_TRANSITION_TPE

    @property
    def binds_subsequent_year_if_post_season(self) -> bool:
        """
        Sec. 2(e)(2)(ii): rows E-J executed after the Regular Season restrict the
        *following* Salary Cap Year rather than the current one.
        """
        return "E" <= self.value <= "J"


_ROW_DESCRIPTIONS: dict[RestrictionRow, str] = {
    RestrictionRow.A_BI_ANNUAL: "sign or acquire a player using the Bi-annual Exception",
    RestrictionRow.B_NON_TAXPAYER_MLE: (
        "sign or acquire a player using the Non-Taxpayer Mid-Level Exception"
    ),
    RestrictionRow.C_SIGN_AND_TRADE_IN: (
        "acquire a player on a contract signed under Art. VII 8(e)(1), i.e. take in a "
        "sign-and-trade"
    ),
    RestrictionRow.D_WAIVED_PLAYER_ABOVE_MLE: (
        "sign a player waived during the Season whose pre-waiver salary exceeded the "
        "Non-Taxpayer Mid-Level"
    ),
    RestrictionRow.E_EXPANDED_TPE: "acquire a player using an Expanded Traded Player Exception",
    RestrictionRow.F_POST_SEASON_STANDARD_TPE: (
        "use a Standard Traded Player Exception created in a prior Salary Cap Year"
    ),
    RestrictionRow.G_TRANSITION_TPE: (
        "acquire a player using a Transition Traded Player Exception"
    ),
    RestrictionRow.H_AGGREGATED_TPE: (
        "acquire a player using an exception created by aggregating two or more contracts"
    ),
    RestrictionRow.I_CASH_PAID: "send cash to another team in a trade",
    RestrictionRow.J_TPE_FROM_SIGN_AND_TRADE: (
        "use a Traded Player Exception created by a signed-and-traded contract"
    ),
    RestrictionRow.K_TAXPAYER_MLE: "sign a player using the Taxpayer Mid-Level Exception",
}


class SeasonThresholds:
    """Minimal view of a Season needed to price an apron level."""

    def __init__(self, first_apron: int, second_apron: int) -> None:
        self.first_apron = first_apron
        self.second_apron = second_apron

    def amount_for(self, level: ApronLevel) -> int:
        return self.first_apron if level is ApronLevel.FIRST else self.second_apron


@dataclass(frozen=True, slots=True)
class HardCapCeiling:
    """
    One ceiling, created by one transaction.

    `row` and `effective_date` may be unknown: SalarySwish publishes the apron
    level and the triggering transaction but neither the Transaction
    Restrictions Table row nor the date. The level is what sets the dollar
    figure, so a ceiling with an unknown row still binds correctly.
    """

    row: RestrictionRow | None
    level: ApronLevel
    effective_date: date | None
    season_id: str
    source_transaction: str | None = None

    def describe(self) -> str:
        where = f" ({self.source_transaction})" if self.source_transaction else ""
        via = f"row {self.row.value}" if self.row else "a row not published by the source"
        return f"{self.level.value} via {via}{where}"


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
