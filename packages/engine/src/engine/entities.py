"""Teams and players (task 1.2)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .provenance import Provenance


@dataclass(frozen=True, slots=True)
class Team:
    team_id: str
    name: str
    abbreviation: str
    conference: str | None = None
    division: str | None = None


@dataclass(frozen=True, slots=True)
class Player:
    player_id: str
    name: str
    years_of_service: int
    birth_date: date | None = None
    draft_year: int | None = None
    draft_round: int | None = None
    draft_pick: int | None = None
    bbref_id: str | None = None
    provenance: Provenance | None = None

    def age_on(self, when: date) -> int | None:
        if self.birth_date is None:
            return None
        had_birthday = (when.month, when.day) >= (self.birth_date.month, self.birth_date.day)
        return when.year - self.birth_date.year - (0 if had_birthday else 1)

    def turns_38_before(self, when: date) -> bool | None:
        """
        Over-38 Rule input (Art. VII 3(a)(2)). Note the rule ALSO requires the
        contract to cover four or more Seasons -- age alone does not trigger it.
        """
        age = self.age_on(when)
        return None if age is None else age >= 38
