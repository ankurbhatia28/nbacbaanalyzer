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
from .max_salary import MaximumSalary, MaxTier, maximum_annual_salary, tier_for
from .maybe import Assumption, AssumptionLog, Maybe, State, UnknownValueError
from .picks import ConveyanceOutcome, DraftPick, PickInventory, Protection, SwapRight
from .provenance import Provenance, Source
from .restrictions import RestrictionReason, TradeRestriction
from .roster import RosterState
from .salary_matching import Allowance, MatchingExceptionKind, best_allowance
from .season import Season
from .team_state import TeamState
from .trade import PickAsset, Trade, TradeLeg
from .trade_exceptions import TPEKind, TradeException
from .validate import (
    Constraint,
    ConstraintReport,
    team_trade_constraints,
    validate_trade,
)
from .violations import Code, Verdict, Violation

__all__ = [
    "Allowance",
    "ApronLevel",
    "ApronStatus",
    "Assumption",
    "AssumptionLog",
    "BirdRights",
    "CapHold",
    "CeilingSet",
    "Code",
    "Constraint",
    "ConstraintReport",
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
    "MatchingExceptionKind",
    "MaxTier",
    "MaximumSalary",
    "Maybe",
    "OptionType",
    "PickAsset",
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
    "Trade",
    "TradeException",
    "TradeLeg",
    "TradeRestriction",
    "UnknownValueError",
    "Verdict",
    "Violation",
    "best_allowance",
    "classify",
    "maximum_annual_salary",
    "team_trade_constraints",
    "tier_for",
    "validate_trade",
]
