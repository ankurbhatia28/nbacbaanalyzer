"""Traded Player Exceptions (task 1.8)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from .apron import ApronStatus
from .provenance import Provenance


class TPEKind(StrEnum):
    STANDARD = "standard"
    EXPANDED = "expanded"  # row E -- what hard-capped Milwaukee
    TRANSITION = "transition"
    AGGREGATED = "aggregated"  # row H
    DISABLED_PLAYER = "disabled_player"


@dataclass(frozen=True, slots=True)
class TradeException:
    """
    Whether a TPE is usable depends on the holder's apron status and on when it
    was created -- a second-apron team may not use one from a prior season.

    Note the real data trap: Fanspo's `fromTeamId` is the counterparty, not the
    holder, and its `isActive` flag is stale. Attribute by source page and
    recompute expiry.
    """

    holder_team_id: str
    amount: int
    created: date
    expires: date
    kind: TPEKind = TPEKind.STANDARD
    amount_used: int = 0
    origin_player_id: str | None = None
    reason: str | None = None
    provenance: Provenance | None = None

    @property
    def remaining(self) -> int:
        return max(0, self.amount - self.amount_used)

    def is_live(self, on: date) -> bool:
        return on <= self.expires and self.remaining > 0

    def arose_in_prior_season(self, season_start_year: int) -> bool:
        return self.created.year < season_start_year

    def usable_by(self, status: ApronStatus, on: date, season_start_year: int) -> bool:
        if not self.is_live(on):
            return False
        return not (
            status is ApronStatus.SECOND_APRON and self.arose_in_prior_season(season_start_year)
        )
