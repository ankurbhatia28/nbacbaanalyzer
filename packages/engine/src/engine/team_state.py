"""A team's complete position at a point in time."""

from __future__ import annotations

from dataclasses import dataclass, field

from .apron import ApronStatus, CeilingSet, SeasonThresholds, classify
from .contract import Contract
from .holds import CapHold, DeadMoney, HoldKind
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
        The figure the aprons and the Transaction Restrictions Table measure.

        Art. VII §2(e)(1), p. 187: Team Salary, minus Free Agent Amounts (iv),
        minus unsigned First Round Pick amounts (vi), minus incomplete-roster
        amounts (x), plus a Restricted Free Agent's outstanding Qualifying
        Offer (v). So **cap holds count against the cap but not the aprons** --
        except a restricted free agent's, which counts at the Qualifying Offer.

        This was `cap_salary()` until Phase 7, which put every team carrying
        free-agent holds over aprons it was not over: Denver's $41.9M of holds
        made a $208.7M taxpayer read as a second-apron team.

        Not modelled, and absent rather than approximated: performance bonuses
        excluded from Salary (i), zero- and one-year Free Agent contracts (ii),
        §4(a)(1)(iii) amounts (iii), Required Tenders (vii), exceptions deemed
        included (viii) and §4(l) exclusions (ix). None is carried by any
        source this project reads.
        """
        restricted = sum(
            h.qualifying_offer if h.qualifying_offer else h.amount
            for h in self.cap_holds
            if h.kind is HoldKind.QUALIFYING_OFFER
        )
        return self.committed_salary() + sum(d.amount for d in self.dead_money) + restricted

    # -- position --------------------------------------------------------
    def apron_status(self) -> ApronStatus:
        """
        Where the team sits. Whether it has room is a *cap* question, so it is
        asked of cap salary, holds included; the tax line and the aprons are
        asked of Apron Team Salary.
        """
        if self.cap_salary() < self.season.salary_cap:
            return ApronStatus.ROOM
        status = classify(
            self.apron_team_salary(),
            self.season.salary_cap,
            self.season.tax_level,
            self.season.first_apron,
            self.season.second_apron,
        )
        return ApronStatus.OVER_CAP if status is ApronStatus.ROOM else status

    def thresholds(self) -> SeasonThresholds:
        return SeasonThresholds(self.season.first_apron, self.season.second_apron)

    def effective_ceiling(self) -> tuple[str, int] | None:
        """The binding hard-cap ceiling, or None. Distinct from apron_status."""
        got = self.ceilings.effective(self.thresholds())
        return (got[0].value, got[1]) if got else None

    def room_below_ceiling(self) -> int | None:
        got = self.ceilings.effective(self.thresholds())
        return None if got is None else got[1] - self.apron_team_salary()
