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
    numbers. Denver is the worked example: $208.7M of active salary plus $41.9M
    of holds is $250.6M against the cap, but Art. VII §2(e)(1)(iv) takes
    Free Agent Amounts back out of Apron Team Salary, so for the aprons Denver
    is at $208.7M -- a taxpayer, below the first apron.
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
