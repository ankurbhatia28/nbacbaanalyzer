"""
NBA CBA rules engine.

Pure functions over the domain model. This package imports no LLM client --
enforced by CI and by tests/test_architecture.py. See ADR-001.
"""

from .apron import (
    ApronLevel,
    ApronStatus,
    CeilingSet,
    HardCapCeiling,
    RestrictionRow,
    SeasonThresholds,
    classify,
)
from .contract import (
    Contract,
    ContractOption,
    ContractType,
    ContractYear,
    Guarantee,
    GuaranteeType,
    OptionType,
)
from .entities import Player, Team
from .holds import BirdRights, CapHold, DeadMoney, HoldKind
from .maybe import Assumption, AssumptionLog, Maybe, State, UnknownValueError
from .picks import ConveyanceOutcome, DraftPick, PickInventory, Protection, SwapRight
from .provenance import Provenance, Source
from .restrictions import RestrictionReason, TradeRestriction
from .roster import RosterState
from .season import Season
from .team_state import TeamState
from .trade_exceptions import TPEKind, TradeException

__all__ = [
    "ApronLevel",
    "ApronStatus",
    "Assumption",
    "AssumptionLog",
    "BirdRights",
    "CapHold",
    "CeilingSet",
    "Contract",
    "ContractOption",
    "ContractType",
    "ContractYear",
    "ConveyanceOutcome",
    "DeadMoney",
    "DraftPick",
    "Guarantee",
    "GuaranteeType",
    "HardCapCeiling",
    "HoldKind",
    "Maybe",
    "OptionType",
    "PickInventory",
    "Player",
    "Protection",
    "Provenance",
    "RestrictionReason",
    "RestrictionRow",
    "RosterState",
    "Season",
    "SeasonThresholds",
    "Source",
    "State",
    "SwapRight",
    "TPEKind",
    "Team",
    "TeamState",
    "TradeException",
    "TradeRestriction",
    "UnknownValueError",
    "classify",
]
