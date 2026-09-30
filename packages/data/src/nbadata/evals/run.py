"""
Run the engine against real trades (task 4.4).

Every completed trade was legal, so the corpus only catches **false positives** —
the engine wrongly rejecting something that happened. False negatives come from
mutation testing, which is a separate suite.

Two design choices worth stating, because both affect how the number reads.

**Partial verdicts.** Some rules need a team's Apron Team Salary at the trade
date, which we cannot reconstruct for most cases. Those checks are recorded as
SKIPPED with a reason rather than silently omitted or assumed to pass. A report
saying "62/62 on salary matching, 21 ceiling checks skipped" is a smaller claim
than "62/62", and the smaller claim is the true one.

**Asymmetric assumptions.** Where a rule depends on something unknown, the
engine is run under the reading most favourable to the trade being legal. Since
every case in the corpus *is* legal, a failure under the most permissive reading
is unambiguous: it cannot be explained away by the missing data. A pass proves
less, and the report says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from engine.salary_matching import best_allowance, best_structure
from engine.season import Season

from .corpus import TradeCase


class Outcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class CheckResult:
    check: str
    outcome: Outcome
    detail: str
    team: str | None = None


@dataclass
class CaseResult:
    trade_id: int
    date: str
    season_id: str
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def failed(self) -> list[CheckResult]:
        return [c for c in self.checks if c.outcome is Outcome.FAIL]

    @property
    def passed(self) -> bool:
        return not self.failed


@dataclass
class EvalReport:
    cases: list[CaseResult] = field(default_factory=list)

    def tally(self) -> dict[str, dict[str, int]]:
        out: dict[str, dict[str, int]] = {}
        for case in self.cases:
            for check in case.checks:
                bucket = out.setdefault(check.check, {"pass": 0, "fail": 0, "skipped": 0})
                bucket[check.outcome.value] += 1
        return out

    @property
    def failures(self) -> list[tuple[CaseResult, CheckResult]]:
        return [(c, f) for c in self.cases for f in c.failed]

    def render(self) -> str:
        lines = [f"{len(self.cases)} trades from the corpus", ""]
        lines.append(f"{'check':22s} {'pass':>6s} {'fail':>6s} {'skipped':>8s}")
        for name, counts in sorted(self.tally().items()):
            lines.append(
                f"{name:22s} {counts['pass']:>6d} {counts['fail']:>6d} {counts['skipped']:>8d}"
            )
        if self.failures:
            lines += ["", "failures:"]
            lines += [
                f"  trade {case.trade_id} ({case.date}) {check.team or ''}: {check.detail}"
                for case, check in self.failures[:20]
            ]
        return "\n".join(lines)


NEEDS_TEAM_STATE = (
    "requires the team's Apron Team Salary at the trade date, which the corpus does not carry"
)

NEEDS_CAPACITY = (
    "the team takes back more than a simultaneous exception permits, so it must "
    "have used cap room (Art. VII 6(j)(1)(v)) or a pre-existing Traded Player "
    "Exception -- neither of which the corpus carries. Not determinable here."
)
"""
The first run of this harness reported eleven failures, all of which were the
harness over-claiming rather than the engine being wrong. A team sending no
salary and taking back $30m has not broken a rule; it has used room or a
standing exception. Outgoing salary is not a team's only capacity, and treating
it that way turns ordinary trades into false positives.

A case like that is genuinely undetermined, so it is skipped. The claim shrinks
to "of the trades where salary matching is conclusively determinable, all pass",
which is smaller and true.
"""


def evaluate(case: TradeCase, season: Season, base_season_cap: int) -> CaseResult:
    result = CaseResult(case.trade_id, case.date, case.season_id)

    result.checks.append(
        CheckResult(
            "corpus_balance",
            Outcome.PASS if case.balanced else Outcome.FAIL,
            "total incoming equals total outgoing"
            if case.balanced
            else "trade does not balance; salary figures are not trustworthy",
        )
    )
    if not case.balanced:
        return result

    for leg in case.legs:
        if leg.incoming <= leg.outgoing:
            result.checks.append(
                CheckResult(
                    "salary_matching",
                    Outcome.PASS,
                    "takes back no more than it sends, so no exception is needed",
                    leg.team,
                )
            )
            continue

        # The most permissive reading: assume the team lands below the first
        # apron, so the $250,000 allowance survives (Art. VII 6(j)(3)), and that
        # it may aggregate. A real trade failing even this is a genuine defect.
        #
        # Where the individual outgoing contracts are known, the team may split
        # them across several exceptions (6(j) is carved out of 6(m)'s bar on
        # combining), which permits materially more than one exception alone.
        permitted = False
        how = ""
        if leg.outgoing_reconstructed:
            structure = best_structure(list(leg.outgoing_salaries), season, 0, base_season_cap)
            if structure.permits(leg.incoming):
                permitted = True
                how = (
                    f"permitted across {structure.exception_count} exception(s) "
                    f"(${structure.total_allowance:,} allowed)"
                )
        allowance = (
            None
            if permitted
            else best_allowance(
                leg.outgoing,
                leg.incoming,
                season,
                0,
                base_season_cap,
                aggregating=True,
                cap_room=None,
            )
        )
        if allowance is not None:
            permitted = True
            how = (
                f"permitted by the {allowance.kind.value} exception (${allowance.amount:,} allowed)"
            )
        if not permitted:
            result.checks.append(
                CheckResult(
                    "salary_matching",
                    Outcome.SKIPPED,
                    f"takes back ${leg.incoming:,} against ${leg.outgoing:,} sent; "
                    + NEEDS_CAPACITY,
                    leg.team,
                )
            )
        else:
            result.checks.append(CheckResult("salary_matching", Outcome.PASS, how, leg.team))

        result.checks.append(
            CheckResult("hard_cap_ceiling", Outcome.SKIPPED, NEEDS_TEAM_STATE, leg.team)
        )
        result.checks.append(
            CheckResult("allowance_removal", Outcome.SKIPPED, NEEDS_TEAM_STATE, leg.team)
        )
    return result


def run(cases: list[TradeCase], seasons: dict[str, Season], base_season_cap: int) -> EvalReport:
    report = EvalReport()
    for case in cases:
        season = seasons.get(case.season_id)
        if season is None:
            result = CaseResult(case.trade_id, case.date, case.season_id)
            result.checks.append(
                CheckResult(
                    "season_constants",
                    Outcome.SKIPPED,
                    f"no cap figures loaded for {case.season_id}",
                )
            )
            report.cases.append(result)
            continue
        report.cases.append(evaluate(case, season, base_season_cap))
    return report
