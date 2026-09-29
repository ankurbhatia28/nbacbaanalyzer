"""A team's complete position at a point in time."""

from __future__ import annotations

from dataclasses import dataclass, field

from .apron import ApronStatus, CeilingSet, SeasonThresholds, classify
from .contract import Contract
from .holds import CapHold, DeadMoney
from .picks import PickInventory
from .provenance import Provenance
from .restrictions import TradeRestriction
from .roster import RosterState
from .season import Season
from .trade_exceptions import TradeException


@dataclass
class TeamState:
    """
    Everything the rules engine needs about one team for one season.

    The three salary totals are deliberately separate methods rather than one
    `salary` property, because they diverge and the divergence changes answers.
    """

    team_id: str
    season: Season
    contracts: list[Contract] = field(default_factory=list)
    cap_holds: list[CapHold] = field(default_factory=list)
    dead_money: list[DeadMoney] = field(default_factory=list)
    trade_exceptions: list[TradeException] = field(default_factory=list)
    restrictions: list[TradeRestriction] = field(default_factory=list)
    picks: PickInventory | None = None
    roster: RosterState | None = None
    ceilings: CeilingSet = field(default_factory=CeilingSet)
    provenance: Provenance | None = None

    # -- the three totals ------------------------------------------------
    def committed_salary(self) -> int:
        """Players under contract only. Not a cap concept, but what most sources publish."""
        return sum(c.cap_figure(self.season.season_id) for c in self.contracts)

    def cap_salary(self) -> int:
        """Includes cap holds and dead money. What determines room."""
        return (
            self.committed_salary()
            + sum(h.amount for h in self.cap_holds)
            + sum(d.amount for d in self.dead_money)
        )

    def apron_team_salary(self) -> int:
        """
        The figure the Transaction Restrictions Table measures against.

        Placeholder: currently equals cap salary. Task 3.2 refines this -- apron
        salary diverges from cap salary on likely bonuses and on how certain
        exceptions are counted.
        """
        return self.cap_salary()

    # -- position --------------------------------------------------------
    def apron_status(self) -> ApronStatus:
        return classify(
            self.apron_team_salary(),
            self.season.salary_cap,
            self.season.tax_level,
            self.season.first_apron,
            self.season.second_apron,
        )

    def thresholds(self) -> SeasonThresholds:
        return SeasonThresholds(self.season.first_apron, self.season.second_apron)

    def effective_ceiling(self) -> tuple[str, int] | None:
        """The binding hard-cap ceiling, or None. Distinct from apron_status."""
        got = self.ceilings.effective(self.thresholds())
        return (got[0].value, got[1]) if got else None

    def room_below_ceiling(self) -> int | None:
        got = self.ceilings.effective(self.thresholds())
        return None if got is None else got[1] - self.apron_team_salary()
