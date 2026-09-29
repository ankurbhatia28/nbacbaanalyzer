"""Cap holds and Bird rights (tasks 1.5, 1.6)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .provenance import Provenance


class BirdRights(StrEnum):
    """Accrued by consecutive seasons without clearing waivers; transfers in a trade."""

    FULL = "Bird"
    EARLY = "Early Bird"
    NON = "Non-Bird"
    NONE = "None"


class HoldKind(StrEnum):
    FREE_AGENT = "free_agent"
    QUALIFYING_OFFER = "qualifying_offer"
    DRAFT_PICK = "draft_pick"
    INCOMPLETE_ROSTER = "incomplete_roster"
    TWO_WAY = "two_way"


@dataclass(frozen=True, slots=True)
class CapHold:
    """
    Holds are why cap salary, tax salary and apron salary are three different
    numbers. Denver is the worked example: $208.7M of active salary sits under
    the second apron, and $250.6M with holds sits well over it.
    """

    kind: HoldKind
    amount: int
    player_id: str | None = None
    description: str | None = None
    bird_rights: BirdRights = BirdRights.NONE
    qualifying_offer: int | None = None
    provenance: Provenance | None = None


@dataclass(frozen=True, slots=True)
class DeadMoney:
    amount: int
    player_id: str | None = None
    description: str | None = None
