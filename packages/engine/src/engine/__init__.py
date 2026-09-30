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
from .apron_restrictions import (
    TransactionPermission,
    available_transactions,
    barred_transactions,
    explain_apron_position,
    may_engage,
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
from .draft_pick_penalty import PickPenaltyStatus, frozen_draft_year
from .entities import Player, Team
from .holds import BirdRights, CapHold, DeadMoney, HoldKind
from .max_salary import MaximumSalary, MaxTier, maximum_annual_salary, tier_for
from .maybe import Assumption, AssumptionLog, Maybe, State, UnknownValueError
from .picks import ConveyanceOutcome, DraftPick, PickInventory, Protection, SwapRight
from .poison_pill import (
    Party,
    arenas_applies,
    arenas_offer_sheet_room_value,
    rookie_extension_trade_value,
)
from .provenance import Provenance, Source
from .restrictions import RestrictionReason, TradeRestriction
from .roster import RosterState
from .salary_matching import Allowance, MatchingExceptionKind, best_allowance
from .season import Season
from .team_state import TeamState
from .trade import PickAsset, Trade, TradeLeg
from .trade_dates import TradeBarReason, TradeEligibility
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
    "Party",
    "PickAsset",
    "PickInventory",
    "PickPenaltyStatus",
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
    "TradeBarReason",
    "TradeEligibility",
    "TradeException",
    "TradeLeg",
    "TradeRestriction",
    "TransactionPermission",
    "UnknownValueError",
    "Verdict",
    "Violation",
    "arenas_applies",
    "arenas_offer_sheet_room_value",
    "available_transactions",
    "barred_transactions",
    "best_allowance",
    "classify",
    "explain_apron_position",
    "frozen_draft_year",
    "maximum_annual_salary",
    "may_engage",
    "rookie_extension_trade_value",
    "team_trade_constraints",
    "tier_for",
    "validate_trade",
]
