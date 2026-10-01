"""
Ground-truth evaluation against real trades.

The corpus is self-labelling: every completed trade was legal when it happened,
so no annotation is needed and no case is disputable. That catches false
positives -- the engine rejecting something real. False negatives need mutation
testing, which is a separate suite.
"""

from .corpus import Leg, TradeCase, load
from .mutate import Mutant, MutationKind, generate
from .run import CaseResult, CheckResult, EvalReport, Outcome, evaluate, run
from .score import Detection, Score, score
from .seasons import load_seasons

__all__ = [
    "CaseResult",
    "CheckResult",
    "Detection",
    "EvalReport",
    "Leg",
    "Mutant",
    "MutationKind",
    "Outcome",
    "Score",
    "TradeCase",
    "evaluate",
    "generate",
    "load",
    "load_seasons",
    "run",
    "score",
]
