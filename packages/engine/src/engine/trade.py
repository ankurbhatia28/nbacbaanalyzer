"""A proposed trade, in the shape the engine validates."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .contract import Contract


@dataclass(frozen=True, slots=True)
class PickAsset:
    year: int
    round_: int
    original_team_id: str


@dataclass
class TradeLeg:
    """
    What one team sends and receives.

    Each team is validated independently rather than the deal being netted out:
    Art. VII 6(j) measures a team's own outgoing against its own incoming, and a
    three-team deal that nets to zero can still be illegal for one participant.
    """

    team_id: str
    sends: list[Contract] = field(default_factory=list)
    receives: list[Contract] = field(default_factory=list)
    sends_picks: list[PickAsset] = field(default_factory=list)
    receives_picks: list[PickAsset] = field(default_factory=list)
    cash_paid: int = 0
    cash_received: int = 0

    def outgoing_salary(self, season_id: str) -> int:
        return sum(c.cap_figure(season_id) for c in self.sends)

    def incoming_salary(self, season_id: str) -> int:
        return sum(c.cap_figure(season_id) for c in self.receives)

    @property
    def is_aggregating(self) -> bool:
        """Two or more outgoing contracts, which changes which exception applies."""
        return len(self.sends) >= 2


@dataclass
class Trade:
    legs: list[TradeLeg]
    as_of: date
    season_id: str

    @property
    def team_ids(self) -> list[str]:
        return [leg.team_id for leg in self.legs]

    def leg_for(self, team_id: str) -> TradeLeg | None:
        return next((leg for leg in self.legs if leg.team_id == team_id), None)
