"""
Violation codes and the citation each one resolves to (task 3.17).

This table is the join between the deterministic engine and the retrieval layer.
The engine decides *that* a rule was broken and *which* one; retrieval fetches
that provision's text verbatim. The model quotes it. It never chooses which rule
applies, which is why these citations are right where a pure-RAG system's would
merely be plausible.

Only codes for rules actually read from the document appear here. A code without
a verified citation would be a guess wearing a reference.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from . import citations
from .citations import Citation
from .maybe import Assumption


class Code(StrEnum):
    SALARY_MATCHING_EXCEEDED = "salary_matching_exceeded"
    NO_EXCEPTION_AVAILABLE = "no_exception_available"
    HARD_CAP_CEILING_EXCEEDED = "hard_cap_ceiling_exceeded"
    AGGREGATION_TWO_MONTH_BAR = "aggregation_two_month_bar"
    PLAYER_TRADE_RESTRICTED = "player_trade_restricted"
    ROSTER_MAXIMUM_EXCEEDED = "roster_maximum_exceeded"
    APRON_TRANSACTION_BARRED = "apron_transaction_barred"


CITATION_FOR: dict[Code, Citation] = {
    Code.SALARY_MATCHING_EXCEEDED: citations.TPE_STANDARD,
    Code.NO_EXCEPTION_AVAILABLE: citations.TPE_EXPANDED,
    Code.HARD_CAP_CEILING_EXCEEDED: citations.TRANSACTION_RESTRICTIONS,
    Code.AGGREGATION_TWO_MONTH_BAR: citations.AGGREGATION_TWO_MONTH_BAR,
    Code.PLAYER_TRADE_RESTRICTED: citations.TRADE_RULES,
    Code.ROSTER_MAXIMUM_EXCEEDED: citations.TRADE_RULES,
    Code.APRON_TRANSACTION_BARRED: citations.TRANSACTION_PROHIBITION,
}


@dataclass(frozen=True, slots=True)
class Violation:
    code: Code
    team_id: str
    detail: str
    subject: str | None = None

    @property
    def citation(self) -> Citation:
        return CITATION_FOR[self.code]

    def describe(self) -> str:
        who = f" ({self.subject})" if self.subject else ""
        return f"{self.team_id}{who}: {self.detail} [{self.citation}]"


@dataclass
class Verdict:
    """
    The result of validating a trade.

    `assumptions` is not decoration. A verdict resting on an unknown trade kicker
    is not the same claim as one resting on a known absence, and collapsing the
    two is the failure ADR-003 exists to prevent. A caller that ignores this
    field is reading a number more confident than the data supports.
    """

    legal: bool
    violations: list[Violation] = field(default_factory=list)
    assumptions: list[Assumption] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def is_conditional(self) -> bool:
        """True when the verdict depends on something no source could tell us."""
        return bool(self.assumptions)

    def summary(self) -> str:
        head = "legal" if self.legal else "illegal"
        if self.violations:
            head += ": " + "; ".join(v.detail for v in self.violations)
        if self.assumptions:
            head += " — " + "; ".join(a.describe() for a in self.assumptions)
        return head
