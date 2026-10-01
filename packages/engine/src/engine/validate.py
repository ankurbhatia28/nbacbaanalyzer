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

from . import trade_dates
from .apron import ApronStatus
from .apron_restrictions import barred_transactions
from .citations import (
    AGGREGATION_TWO_MONTH_BAR,
    TPE_STANDARD,
    TRADE_RULES,
    TRANSACTION_RESTRICTIONS,
    Citation,
)
from .constitution import FIRST_ROUND_DRAFT_CHOICE, ByLaw, check_first_round_rule
from .contract import ContractType
from .maybe import Assumption, AssumptionLog
from .roster import STANDARD_MAX, STANDARD_MIN
from .salary_matching import Allowance, best_allowance, best_structure
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

CONSTRAINTS_ENUMERATED = (
    "hard cap ceilings (Art. VII 2(e)(2)(i)(B))",
    "apron transaction restrictions (Art. VII 2(e)(2)(i)(A))",
    "player trade restrictions",
    "trade-date windows (Art. VII 8(d))",
    "first-round pick tradeability (By-Law 7.03)",
    "roster minimum",
    "take-back capacity (Art. VII 6(j))",
    "trade bonus and no-trade clause, where known",
)
"""What team_trade_constraints enumerates. Same contract as CHECKS_IMPLEMENTED:
an empty constraint list means 'nothing found among these', not 'unrestricted'.

Not covered, and absent rather than approximated:
  * Art. VII 2(f), the Second Apron Team draft pick freeze -- not implemented
  * the seven-Drafts-ahead pick horizon -- see constitution.PICK_HORIZON_NOT_SOURCED
"""

AGGREGATION_BAR = timedelta(days=60)


def _incoming_with_kickers(leg: TradeLeg, season_id: str, log: AssumptionLog) -> int:
    """
    Incoming salary, with trade kickers folded in.

    Who pays the bonus and whose Team Salary it lands in are different
    questions, and only the second one matters here. The **sending** team pays
    the player (Art. XXIV §2(a), p. 438), but the bonus is added to the
    **acquiring** team's Team Salary and counts as incoming trade salary for
    matching -- which is why it is applied to `leg.receives`. Teams may alter
    the payment arrangement between themselves, but that is governed by the
    cash-in-trade rules (Art. VII §8(a)) and does not move the cap hit.

    A kicker raises what the acquiring team takes back, so an unknown one can
    flip a verdict. We assume absent -- and record that -- rather than treating
    unknown as zero silently (ADR-003).

    Not modelled: a player may agree to reduce or waive the bonus to make the
    math work (Art. XXIV §2(a)(iii)(B)(3), p. 439). So a trade that fails *only*
    on a kicker is conditional rather than illegal, which is why the constraint
    report says so rather than calling it blocking.
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
    citation: Citation | ByLaw | None = None
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
    state: TeamState,
    *,
    player_id: str | None = None,
    as_of: date | None = None,
    base_season_cap: int | None = None,
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
                        "acquiring team must absorb; he may agree to reduce or waive it, so "
                        "a deal that fails only on the bonus is not necessarily dead",
                    )
                )

    _add_apron_restrictions(report, state)
    _add_pick_constraints(report, state)
    _add_roster_constraints(report, state)
    if player_id:
        _add_trade_window(report, state, player_id, when, log)
        _add_no_trade_clause(report, state, player_id, log)
        _add_capacity(report, state, player_id, base_season_cap)

    report.assumptions = log.entries
    return report


def _add_apron_restrictions(report: ConstraintReport, state: TeamState) -> None:
    """
    The Transaction Restrictions Table rows this team may not use.

    This is the substance of "what are the limitations" -- being over an apron
    does not stop a team trading, it stops it trading in particular *ways*. The
    rows are derived from Art. VII 2(e)(2)(i)(A) rather than transcribed.

    Measured on current Apron Team Salary with nothing added, which is the
    question being asked: what could this team do at all? A specific deal is
    judged on where its salary would land afterwards, which is validate_trade's
    job rather than this one's.
    """
    barred = barred_transactions(apron_salary=state.apron_team_salary(), season=state.season)
    for permission in barred:
        report.constraints.append(
            Constraint(
                "apron_restriction",
                f"may not {permission.row.describe()} "
                f"(over the {permission.applicable_level.value.replace('_', ' ')} of "
                f"${permission.level_amount:,})",
                permission.citation,
            )
        )
    if not barred:
        report.constraints.append(
            Constraint("apron_restriction", "no apron transaction restrictions apply")
        )


def _add_pick_constraints(report: ConstraintReport, state: TeamState) -> None:
    """
    Which first-round picks By-Law 7.03 lets this team trade.

    Asked one pick at a time: trading *this* first is barred when doing so would
    leave the team without a first in two consecutive Drafts. A team can be free
    to trade one year's first and barred from trading another's, so a single
    yes/no over the whole inventory would be wrong.
    """
    inventory = state.picks
    if inventory is None:
        report.constraints.append(
            Constraint("picks", "pick inventory not loaded; tradeability not assessed")
        )
        return

    years = sorted({p.year for p in inventory.picks if p.round_ == 1})
    if not years:
        return
    span = range(years[0], years[-1] + 1)
    held = {y: inventory.has_first_in(y) for y in span}

    forfeited = sorted({p.year for p in inventory.picks if p.round_ == 1 and p.forfeited})
    if forfeited:
        report.constraints.append(
            Constraint(
                "forfeited_picks",
                "first-round picks forfeited in " + ", ".join(str(y) for y in forfeited),
            )
        )

    untradeable = []
    for year in span:
        if not held[year]:
            continue
        without = dict(held)
        without[year] = False
        if not check_first_round_rule(years_examined=span, holds_first_in=without).permitted:
            untradeable.append(year)

    if untradeable:
        report.constraints.append(
            Constraint(
                "stepien",
                "may not trade its "
                + ", ".join(str(y) for y in untradeable)
                + " first-round pick; doing so would leave two consecutive Drafts "
                "without one",
                FIRST_ROUND_DRAFT_CHOICE,
            )
        )
    tradeable = [y for y in span if held[y] and y not in untradeable]
    if tradeable:
        report.constraints.append(
            Constraint(
                "stepien",
                "may trade its first-round pick in " + ", ".join(str(y) for y in tradeable),
                FIRST_ROUND_DRAFT_CHOICE,
            )
        )


def _add_roster_constraints(report: ConstraintReport, state: TeamState) -> None:
    """
    A trade that sends out more players than it takes back can drop a team under
    the fourteen-player minimum, which is a real limit on how a deal may be
    shaped even though it bars no trade outright.
    """
    roster = state.roster
    if roster is None:
        return
    spare = roster.standard_count - STANDARD_MIN
    if spare <= 0:
        report.constraints.append(
            Constraint(
                "roster_minimum",
                f"carries {roster.standard_count} standard contracts against a minimum of "
                f"{STANDARD_MIN}; any trade must bring back at least as many players as it sends",
            )
        )
    else:
        report.constraints.append(
            Constraint(
                "roster_minimum",
                f"may send up to {spare} more player(s) than it takes back before reaching "
                f"the {STANDARD_MIN}-player minimum",
            )
        )
    if roster.open_standard_slots == 0:
        report.constraints.append(
            Constraint(
                "roster_maximum",
                f"is at the {STANDARD_MAX}-player maximum; any trade must send out at least "
                "as many players as it takes back",
            )
        )


def _add_trade_window(
    report: ConstraintReport, state: TeamState, player_id: str, when: date, log: AssumptionLog
) -> None:
    """
    Whether this player may be traded today at all (Art. VII 8(d)).

    The flags that decide which bar applies -- signed as a free agent, re-signed
    above 120%, a rookie or two-way deal -- are not all carried on the contract,
    so what is not known is recorded as an assumption rather than taken as false.
    A bar missed here reads as "tradeable", so the gap has to be stated.
    """
    contract = next((c for c in state.contracts if c.player_id == player_id), None)
    if contract is None or contract.signed_date is None:
        report.constraints.append(
            Constraint(
                "trade_window",
                f"signing date for {player_id} is not known, so the Art. VII 8(d) waiting "
                "periods cannot be checked",
                TRADE_RULES,
            )
        )
        log.add(Assumption("signed_date", player_id, None, "not carried for this contract"))
        return

    eligibility = trade_dates.check(
        when=when,
        signed=contract.signed_date,
        is_rookie_or_two_way=contract.contract_type
        in (ContractType.ROOKIE_FIRST_ROUND, ContractType.ROOKIE_SECOND_ROUND),
        signed_as_part_of_sign_and_trade=contract.contract_type is ContractType.SIGN_AND_TRADE,
    )
    if not eligibility.tradeable:
        report.constraints.append(
            Constraint(
                "trade_window",
                f"{player_id} {eligibility.detail}"
                + (
                    f"; eligible from {eligibility.eligible_from:%-d %B %Y}"
                    if eligibility.eligible_from
                    else ""
                ),
                eligibility.citation,
                blocking=True,
            )
        )
    else:
        log.add(
            Assumption(
                "free_agent_or_re_signed_flags",
                player_id,
                False,
                "not carried on the contract; the December 15 and January 15 bars could "
                "not be evaluated",
            )
        )


def _add_no_trade_clause(
    report: ConstraintReport, state: TeamState, player_id: str, log: AssumptionLog
) -> None:
    contract = next((c for c in state.contracts if c.player_id == player_id), None)
    if contract is None:
        return
    if contract.no_trade_clause.is_unknown:
        log.add(
            Assumption(
                "no_trade_clause",
                player_id,
                None,
                "not published by any available source",
            )
        )
        report.constraints.append(
            Constraint(
                "unknown_no_trade_clause",
                f"whether {player_id} holds a no-trade clause is not verifiable from "
                "available sources; one would let him veto any deal",
            )
        )
    elif contract.no_trade_clause.is_known and contract.no_trade_clause.require():
        report.constraints.append(
            Constraint(
                "no_trade_clause",
                f"{player_id} holds a no-trade clause and can veto any deal",
                blocking=True,
            )
        )


def _add_capacity(
    report: ConstraintReport, state: TeamState, player_id: str, base_season_cap: int | None
) -> None:
    """
    How much salary the team could take back for this player.

    The direct answer to "if I wanted to trade X, what are the limitations" --
    a ceiling in dollars, not merely a list of prohibitions.
    """
    contract = next((c for c in state.contracts if c.player_id == player_id), None)
    if contract is None or base_season_cap is None:
        return
    year = next((y for y in contract.years if y.season_id == state.season.season_id), None)
    if year is None:
        return
    structure = best_structure(
        [year.cap_figure], state.season, state.apron_team_salary(), base_season_cap
    )
    report.constraints.append(
        Constraint(
            "take_back_capacity",
            f"sending {player_id} alone (${year.cap_figure:,}) permits taking back up to "
            f"${structure.total_allowance:,} under a simultaneous trade exception",
            TPE_STANDARD,
        )
    )
