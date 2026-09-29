"""League-wide dollar figures, per season (task 1.1)."""

from __future__ import annotations

from dataclasses import dataclass, field

from .provenance import Provenance


@dataclass(frozen=True, slots=True)
class Season:
    """
    Every league-wide threshold for one Salary Cap Year.

    Nothing here belongs hardcoded in rule logic: all of it moves annually, and
    fixtures express boundary cases relative to these values so they keep
    testing boundaries when the figures change.
    """

    season_id: str  # "2026-2027"
    salary_cap: int
    tax_level: int
    first_apron: int
    second_apron: int
    non_taxpayer_mle: int
    taxpayer_mle: int
    room_mle: int
    bi_annual_exception: int
    minimum_scale: dict[int, int] = field(default_factory=dict)  # years of service -> salary
    rookie_scale: dict[int, int] = field(default_factory=dict)  # draft slot -> year-1 salary
    provenance: Provenance | None = None

    @property
    def start_year(self) -> int:
        return int(self.season_id[:4])

    def minimum_for(self, years_of_service: int) -> int:
        """Minimum salary, clamped to the top of the published scale."""
        if not self.minimum_scale:
            raise ValueError(f"no minimum scale loaded for {self.season_id}")
        top = max(self.minimum_scale)
        return self.minimum_scale[min(years_of_service, top)]
