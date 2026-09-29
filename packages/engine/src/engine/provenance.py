"""
Where a fact came from and when it was true.

Task 1.14, and task 7.6 makes it a required UI element: the dataset is a
snapshot, and the Spotrac rows alone span 13 months of differing snapshot dates.
An app that implies currency without showing as-of dates is misleading.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class Source(StrEnum):
    FANSPO = "fanspo"
    BBREF_CONTRACTS = "bbref_contracts"
    BBREF_AWARDS = "bbref_awards"
    BBREF_ROSTER = "bbref_roster"
    SPOTRAC_ARCHIVE = "spotrac_archive"
    SALARYSWISH = "salaryswish"
    CBA_DOCUMENT = "cba_document"
    FIXTURE = "fixture"
    DERIVED = "derived"


@dataclass(frozen=True, slots=True)
class Provenance:
    source: Source
    as_of: date | None = None
    note: str | None = None

    def describe(self) -> str:
        when = f" as of {self.as_of.isoformat()}" if self.as_of else ""
        return f"{self.source.value}{when}"
