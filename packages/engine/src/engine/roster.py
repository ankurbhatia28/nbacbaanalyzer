"""Roster composition limits (task 1.10)."""

from __future__ import annotations

from dataclasses import dataclass

STANDARD_MAX = 15
STANDARD_MIN = 14
TWO_WAY_MAX = 3


@dataclass(frozen=True, slots=True)
class RosterState:
    standard_count: int
    two_way_count: int = 0
    days_below_minimum: int = 0  # a two-week grace period applies

    @property
    def is_over_standard_max(self) -> bool:
        return self.standard_count > STANDARD_MAX

    @property
    def is_below_standard_min(self) -> bool:
        return self.standard_count < STANDARD_MIN

    @property
    def is_over_two_way_max(self) -> bool:
        return self.two_way_count > TWO_WAY_MAX

    @property
    def open_standard_slots(self) -> int:
        return max(0, STANDARD_MAX - self.standard_count)
