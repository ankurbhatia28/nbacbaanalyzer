"""
Trade validation (task 3.18) and constraint enumeration (task 3.19).

Two different questions, deliberately separate tools:

  validate_trade            "is this specific deal legal?"
  team_trade_constraints    "what limits this team in moving this player?"

The second has no proposed deal to check. It answers the Embiid question --
enumerate everything restricting a team right now -- which a validator cannot
express.

Only rules read from the document are enforced. Anything not yet transcribed is
absent rather than approximated, and `Verdict.notes` says which checks ran, so
"legal" is never mistaken for "checked exhaustively".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from .apron import ApronStatus
from .citations import AGGREGATION_TWO_MONTH_BAR, TRANSACTION_RESTRICTIONS, Citation
from .maybe import Assumption, AssumptionLog
from .roster import STANDARD_MAX
from .salary_matching import Allowance, best_allowance
from .team_state import TeamState
from .trade import Trade, TradeLeg
from .violations import Code, Verdict, Violation

CHECKS_IMPLEMENTED = (
    "salary matching (Art. VII 6(j))",
    "hard cap ceilings (Art. VII 2(e)(2)(i)(B))",
    "aggregation two-month bar (Art. VII 6(j)(4)(i))",
    "player trade restrictions",
    "roster maximum",
)
"""What validate_trade actually checks. Reported on every verdict so a caller
cannot read 'legal' as 'nothing else could be wrong'."""

AGGREGATION_BAR = timedelta(days=60)


def _incoming_with_kickers(leg: TradeLeg, season_id: str, log: AssumptionLog) -> int:
    """
    Incoming salary, with trade kickers folded in.

    A kicker raises what the acquiring team takes back, so an unknown one can
    flip a verdict. We assume absent -- and record that -- rather than treating
    unknown as zero silently (ADR-003).
    """
    total = 0
    for contract in leg.receives:
        base = contract.cap_figure(season_id)
        pct = log.read(
            contract.trade_kicker_pct,
            0.0,
            contract.player_id,
            "trade_kicker_pct",
            "not published by any available source",
        )
        total += int(base * (1 + pct))
    return total


def _validate_leg(
    leg: TradeLeg,
    state: TeamState,
    trade: Trade,
    base_season_cap: int,
    log: AssumptionLog,
) -> list[Violation]:
    violations: list[Violation] = []
    season = state.season
    outgoing = leg.outgoing_salary(trade.season_id)
    incoming = _incoming_with_kickers(leg, trade.season_id, log)

    post_salary = state.apron_team_salary() - outgoing + incoming

    # -- salary matching, Art. VII 6(j) --------------------------------
    if incoming > outgoing:
        cap_room = max(0, season.salary_cap - state.cap_salary())
        allowance: Allowance | None = best_allowance(
            outgoing,
            incoming,
            season,
            post_salary,
            base_season_cap,
            aggregating=leg.is_aggregating,
            cap_room=cap_room or None,
        )
        if allowance is None:
            violations.append(
                Violation(
                    Code.NO_EXCEPTION_AVAILABLE,
                    leg.team_id,
                    f"takes back ${incoming:,} against ${outgoing:,} sent; "
                    f"no exception in Art. VII 6(j) permits it",
                )
            )

    # -- hard cap ceilings, Art. VII 2(e)(2)(i)(B) ----------------------
    ceiling = state.ceilings.effective(state.thresholds())
    if ceiling is not None and post_salary > ceiling[1]:
        level, amount = ceiling
        binding = state.ceilings.binding()
        violations.append(
            Violation(
                Code.HARD_CAP_CEILING_EXCEEDED,
                leg.team_id,
                f"post-trade salary ${post_salary:,} exceeds its {level.value.replace('_', ' ')} "
                f"ceiling of ${amount:,}" + (f", set by {binding.describe()}" if binding else ""),
            )
        )

    # -- aggregation bar, Art. VII 6(j)(4)(i) ---------------------------
    if leg.is_aggregating:
        for contract in leg.sends:
            signed = contract.signed_date
            if signed and trade.as_of - signed < AGGREGATION_BAR:
                violations.append(
                    Violation(
                        Code.AGGREGATION_TWO_MONTH_BAR,
                        leg.team_id,
                        f"acquired {(trade.as_of - signed).days} days ago; may not be "
                        "aggregated for two months",
                        subject=contract.player_id,
                    )
                )

    # -- individual trade restrictions ----------------------------------
    restricted = {
        r.player_id
        for r in state.restrictions
        if r.applies_on(trade.as_of) and r.blocks_trade_entirely
    }
    for contract in leg.sends:
        if contract.player_id in restricted:
            reason = next(
                r.reason.value for r in state.restrictions if r.player_id == contract.player_id
            )
            violations.append(
                Violation(
                    Code.PLAYER_TRADE_RESTRICTED,
                    leg.team_id,
                    f"may not be traded ({reason.replace('_', ' ')})",
                    subject=contract.player_id,
                )
            )

    # -- roster maximum --------------------------------------------------
    if state.roster is not None:
        after = state.roster.standard_count - len(leg.sends) + len(leg.receives)
        if after > STANDARD_MAX:
            violations.append(
                Violation(
                    Code.ROSTER_MAXIMUM_EXCEEDED,
                    leg.team_id,
                    f"would hold {after} standard contracts, above the limit of {STANDARD_MAX}",
                )
            )
    return violations


def validate_trade(trade: Trade, states: dict[str, TeamState], base_season_cap: int) -> Verdict:
    """
    Validate each team's own send and receive, not the deal netted out.

    A three-team trade that balances overall can still be illegal for one
    participant, because Art. VII 6(j) measures each team against itself.
    """
    log = AssumptionLog()
    violations: list[Violation] = []
    missing = [t for t in trade.team_ids if t not in states]
    if missing:
        raise KeyError(f"no TeamState supplied for {', '.join(missing)}")

    for leg in trade.legs:
        violations += _validate_leg(leg, states[leg.team_id], trade, base_season_cap, log)

    return Verdict(
        legal=not violations,
        violations=violations,
        assumptions=log.entries,
        notes=[f"checked: {', '.join(CHECKS_IMPLEMENTED)}"],
    )


# ----------------------------------------------------------------------
# Constraint enumeration
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Constraint:
    """One thing limiting a team, with the provision it comes from."""

    kind: str
    detail: str
    citation: Citation | None = None
    blocking: bool = False


@dataclass
class ConstraintReport:
    team_id: str
    apron_status: ApronStatus
    constraints: list[Constraint] = field(default_factory=list)
    assumptions: list[Assumption] = field(default_factory=list)

    @property
    def blocking(self) -> list[Constraint]:
        return [c for c in self.constraints if c.blocking]

    def describe(self) -> str:
        phrase = self.apron_status.value.replace("_", " ")
        article = "an" if phrase[0] in "aeiou" else "a"
        lines = [f"{self.team_id} is {article} {phrase} team."]
        lines += [
            f"  - {c.detail}" + (f" [{c.citation.short}]" if c.citation else "")
            for c in self.constraints
        ]
        return "\n".join(lines)


def team_trade_constraints(
    state: TeamState, *, player_id: str | None = None, as_of: date | None = None
) -> ConstraintReport:
    """
    Everything limiting a team right now, with no deal proposed.

    Answers "if I wanted to trade X, what are the limitations?" -- a question
    validate_trade cannot express, because there is nothing to validate.
    """
    when = as_of or date.today()
    log = AssumptionLog()
    report = ConstraintReport(team_id=state.team_id, apron_status=state.apron_status())

    ceiling = state.ceilings.effective(state.thresholds())
    if ceiling is not None:
        level, amount = ceiling
        headroom = amount - state.apron_team_salary()
        binding = state.ceilings.binding()
        report.constraints.append(
            Constraint(
                "hard_cap",
                f"cannot exceed ${amount:,} ({level.value.replace('_', ' ')}) for the rest of the "
                f"Salary Cap Year — ${headroom:,} of room"
                + (f"; set by {binding.describe()}" if binding else ""),
                TRANSACTION_RESTRICTIONS,
                blocking=headroom <= 0,
            )
        )
        for extra in state.ceilings.ceilings:
            if binding and extra is not binding:
                report.constraints.append(
                    Constraint(
                        "hard_cap_superseded",
                        f"also holds a {extra.level.value.replace('_', ' ')} ceiling from "
                        f"{extra.describe()}, superseded by the lower one",
                        TRANSACTION_RESTRICTIONS,
                    )
                )
    else:
        report.constraints.append(
            Constraint("hard_cap", "holds no hard-cap ceiling this Salary Cap Year")
        )

    for restriction in state.restrictions:
        if not restriction.applies_on(when):
            continue
        if player_id and restriction.player_id != player_id:
            continue
        what = "may not be traded" if restriction.blocks_trade_entirely else "may not be aggregated"
        report.constraints.append(
            Constraint(
                "player_restriction",
                f"{restriction.player_id} {what} ({restriction.reason.value.replace('_', ' ')})",
                AGGREGATION_TWO_MONTH_BAR if restriction.blocks_aggregation_only else None,
                blocking=restriction.blocks_trade_entirely,
            )
        )

    if player_id:
        contract = next((c for c in state.contracts if c.player_id == player_id), None)
        if contract is None:
            report.constraints.append(
                Constraint(
                    "unknown_player",
                    f"{player_id} is not under contract with {state.team_id}",
                    blocking=True,
                )
            )
        else:
            if contract.trade_kicker_pct.is_unknown:
                log.add(
                    Assumption(
                        "trade_kicker_pct",
                        player_id,
                        None,
                        "not published by any available source",
                    )
                )
                report.constraints.append(
                    Constraint(
                        "unknown_trade_kicker",
                        f"whether {player_id} has a trade bonus is not verifiable from "
                        "available sources; a bonus would raise the salary any acquiring team "
                        "must absorb",
                    )
                )
            elif contract.trade_kicker_pct.is_known:
                pct = contract.trade_kicker_pct.require()
                report.constraints.append(
                    Constraint(
                        "trade_kicker",
                        f"{player_id} has a {pct:.0%} trade bonus, raising the salary an "
                        "acquiring team must absorb",
                    )
                )

    report.assumptions = log.entries
    return report
