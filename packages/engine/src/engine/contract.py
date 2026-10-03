"""Contracts, modelled as a row per season (tasks 1.3, 1.4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum

from .maybe import Maybe, UnknownValueError
from .provenance import Provenance


class ContractType(StrEnum):
    """Type selects which rules apply. Values seen in the real data plus CBA kinds."""

    ROOKIE_FIRST_ROUND = "RK-1ST"
    ROOKIE_SECOND_ROUND = "RK-2ND"
    ROOKIE_EXTENSION = "RK-EXT"
    DESIGNATED_ROOKIE_EXTENSION = "DRK-EXT"
    VETERAN = "VET"
    VETERAN_EXTENSION = "VET-EXT"
    DESIGNATED_VETERAN_EXTENSION = "DVET-EXT"
    MAXIMUM = "MAX"
    MINIMUM = "MIN"
    SIGN_AND_TRADE = "S&T"
    REST_OF_SEASON = "ROS"
    TEN_DAY = "10D"
    TWO_WAY = "2W"
    EXHIBIT_9 = "E9"
    EXHIBIT_10 = "E10"
    FREE_AGENT_SIGNING = "FA"
    UNKNOWN = "unknown"
    """No source scraped so far carries contract type (ADR-003). Rules that
    turn on it -- rookie-scale and sign-and-trade bars -- record an assumption."""


class OptionType(StrEnum):
    TEAM = "team"
    PLAYER = "player"
    EARLY_TERMINATION = "eto"


class GuaranteeType(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"
    UNKNOWN = "unknown"
    """No source carries guarantee structure (ADR-003). Not 'full'."""


@dataclass(frozen=True, slots=True)
class Guarantee:
    kind: GuaranteeType
    amount: int | None = None  # for PARTIAL; None means "all of cap_figure" for FULL
    guarantee_date: date | None = None  # the date it becomes fully guaranteed

    def guaranteed_amount(self, cap_figure: int) -> int:
        if self.kind is GuaranteeType.UNKNOWN:
            raise UnknownValueError("guarantee structure is unknown for this contract year")
        if self.kind is GuaranteeType.FULL:
            return cap_figure
        if self.kind is GuaranteeType.NONE:
            return 0
        return self.amount or 0


@dataclass(frozen=True, slots=True)
class ContractOption:
    kind: OptionType
    decision_date: date | None = None
    value: int | None = None
    exercised: bool | None = None  # None = not yet decided


@dataclass(frozen=True, slots=True)
class ContractYear:
    season_id: str
    cap_figure: int
    base_salary: int | None = None
    guarantee: Guarantee = field(default_factory=lambda: Guarantee(GuaranteeType.FULL))
    option: ContractOption | None = None
    likely_incentives: int = 0
    unlikely_incentives: int = 0

    @property
    def guaranteed(self) -> int:
        return self.guarantee.guaranteed_amount(self.cap_figure)


@dataclass(frozen=True, slots=True)
class Contract:
    """
    One player's deal with one team.

    `trade_kicker` and `no_trade_clause` are Maybe because no source we found
    carries them reliably -- see ADR-003. They are never defaulted to absent.
    """

    player_id: str
    team_id: str
    contract_type: ContractType
    years: tuple[ContractYear, ...]
    signed_date: date | None = None
    trade_kicker_pct: Maybe[float] = field(default_factory=Maybe.unknown)
    no_trade_clause: Maybe[bool] = field(default_factory=Maybe.unknown)
    provenance: Provenance | None = None

    @property
    def season_count(self) -> int:
        return len(self.years)

    def year(self, season_id: str) -> ContractYear | None:
        return next((y for y in self.years if y.season_id == season_id), None)

    def cap_figure(self, season_id: str) -> int:
        y = self.year(season_id)
        return y.cap_figure if y else 0

    def covers_season_after_38th_birthday(self, birth_year: int) -> bool:
        """
        Age half of the Over-38 test. The rule ALSO requires four or more
        Seasons -- see `triggers_over_38_rule`.
        """
        return any(int(y.season_id[:4]) - birth_year >= 38 for y in self.years)

    def triggers_over_38_rule(self, birth_year: int) -> bool:
        """
        Art. VII 3(a)(2): applies to a contract that "covers four (4) or more
        Seasons, including one (1) or more Seasons commencing after such player
        will reach or has reached age thirty-eight (38)". Both halves required.
        """
        return self.season_count >= 4 and self.covers_season_after_38th_birthday(birth_year)
