"""Draft picks and their protections (task 1.7)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .provenance import Provenance


class ConveyanceOutcome(StrEnum):
    """What happens when a protected pick lands inside its protected range."""

    ROLL_FORWARD = "roll_forward"
    CONVERT_TO_SECONDS = "convert_to_seconds"
    EXTINGUISH = "extinguish"
    OBLIGATION_LIFTED = "obligation_lifted"


@dataclass(frozen=True, slots=True)
class Protection:
    """
    A predicate over pick slot plus what happens if it does not convey.

    Stored as a range because that is how the source prose reads -- "protected
    for selections 1-4", "top 20 protected", "protected for selections 56-60".
    """

    low: int
    high: int
    outcome: ConveyanceOutcome
    rolls_to_year: int | None = None
    note: str | None = None

    def protects(self, slot: int) -> bool:
        return self.low <= slot <= self.high


@dataclass(frozen=True, slots=True)
class SwapRight:
    """A right to exchange picks, distinct from owning one."""

    holder_team_id: str
    counterparty_team_id: str
    year: int
    round_: int
    most_favorable: bool = True
    note: str | None = None


@dataclass(frozen=True, slots=True)
class DraftPick:
    year: int
    round_: int
    original_team_id: str
    current_owner_team_id: str
    protections: tuple[Protection, ...] = ()
    forfeited: bool = False  # e.g. the Clippers' 2029-2033 firsts
    raw_details: str | None = None
    provenance: Provenance | None = None

    @property
    def is_owned_outright(self) -> bool:
        return (
            not self.forfeited
            and not self.protections
            and self.original_team_id == self.current_owner_team_id
        )

    def conveys_at(self, slot: int) -> bool:
        if self.forfeited:
            return False
        return not any(p.protects(slot) for p in self.protections)


@dataclass
class PickInventory:
    """A team's picks, which is what the Stepien rule actually reasons over."""

    team_id: str
    picks: list[DraftPick] = field(default_factory=list)
    swaps: list[SwapRight] = field(default_factory=list)

    def firsts_in(self, year: int) -> list[DraftPick]:
        """Every first-round record for that year, including ones conveyed away."""
        return [p for p in self.picks if p.round_ == 1 and p.year == year]

    def has_first_in(self, year: int) -> bool:
        """
        Does this team actually hold a first that year?

        Ownership matters, not origin: an inventory legitimately carries records
        of picks the team originated but has since conveyed, and those must not
        count as held. Stepien reasons over what a team *has*.
        """
        return any(
            p.current_owner_team_id == self.team_id and not p.forfeited
            for p in self.firsts_in(year)
        )
