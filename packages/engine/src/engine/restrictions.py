"""Trade restrictions on individual players (task 1.9)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class RestrictionReason(StrEnum):
    RECENTLY_SIGNED = "recently_signed"  # cannot be traded for a period after signing
    RE_SIGNED_WITH_RAISE = "re_signed_with_raise"  # cannot be aggregated for two months
    SIGN_AND_TRADE = "sign_and_trade"
    ONE_YEAR_BIRD_DEAL = "one_year_bird_deal"
    NO_TRADE_CLAUSE = "no_trade_clause"


@dataclass(frozen=True, slots=True)
class TradeRestriction:
    """
    Reason is stored, not just the fact, so a violation can explain itself
    rather than saying only that something is disallowed.
    """

    player_id: str
    reason: RestrictionReason
    expires: date | None = None
    blocks_trade_entirely: bool = True
    blocks_aggregation_only: bool = False

    def applies_on(self, when: date) -> bool:
        return self.expires is None or when <= self.expires
