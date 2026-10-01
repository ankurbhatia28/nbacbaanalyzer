"""
Scoring the mutation suite (task 4.6).

Detection alone is a weak measure: an engine that rejects everything catches
every mutant and is useless. So the suite is scored on two corpora at once.

    recall     mutants detected / mutants generated
               -- does the engine catch what is genuinely broken?

    precision  true detections / (true detections + real trades the engine
               cannot permit) -- does it catch only those?

Reporting recall alone would let a maximally suspicious engine score perfectly,
which is the failure mode this guards against.

Precision here is a **floor, not a measurement**. Its denominator counts every
real trade the engine cannot permit under a simultaneous exception, and most of
those are not errors at all -- the team used cap room or a standing Traded
Player Exception, which the corpus does not carry. Treating each as an error is
the pessimistic reading, so the true precision is at least the figure reported
and probably higher. Saying so is better than quietly excluding them and
claiming a number we cannot support.

Mutants are scored against the **engine** rather than through the eval harness.
The harness reports an over-the-band trade as undetermined, because on real data
it cannot tell an illegal trade from one using cap room. For a mutant we know
which it is, having made it so.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.season import Season
from engine.violations import Code

from .capacity import permits
from .corpus import TradeCase
from .mutate import Mutant, MutationKind


@dataclass(frozen=True, slots=True)
class Detection:
    mutant: Mutant
    detected: bool
    code: Code | None
    correct_reason: bool


@dataclass
class Score:
    detections: list[Detection] = field(default_factory=list)
    undeterminable: int = 0
    """Real trades the engine cannot permit outright. Counted against precision
    as the pessimistic reading; most are cap room or a standing exception."""
    real_cases: int = 0

    @property
    def detected(self) -> int:
        return sum(1 for d in self.detections if d.detected)

    @property
    def right_reason(self) -> int:
        return sum(1 for d in self.detections if d.detected and d.correct_reason)

    @property
    def recall(self) -> float:
        return self.detected / len(self.detections) if self.detections else 0.0

    @property
    def precision_floor(self) -> float:
        total = self.detected + self.undeterminable
        return self.detected / total if total else 0.0

    @property
    def reason_accuracy(self) -> float:
        """Catching a trade for the wrong reason is still a defect."""
        return self.right_reason / self.detected if self.detected else 0.0

    def render(self) -> str:
        missed = [d for d in self.detections if not d.detected]
        lines = [
            f"{len(self.detections)} mutants from real trades, "
            f"{self.real_cases} real trades as the negative control",
            "",
            f"  recall            {self.recall:6.1%}  "
            f"({self.detected}/{len(self.detections)} caught)",
            f"  precision (floor) {self.precision_floor:6.1%}  ({self.undeterminable} real trades "
            f"not permittable outright; most will be cap room or a standing exception)",
            f"  reason accuracy   {self.reason_accuracy:6.1%}  (caught for the stated violation)",
        ]
        if missed:
            lines += ["", "missed:"]
            lines += [
                f"  trade {d.mutant.source_trade_id} {d.mutant.team}: {d.mutant.note}"
                for d in missed[:10]
            ]
        return "\n".join(lines)


def _detect(mutant: Mutant, season: Season, base_cap: int) -> Detection:
    if mutant.kind is MutationKind.UNBALANCE:
        # The harness must reject figures that do not add up before applying
        # any rule to them.
        caught = not mutant.case.balanced
        return Detection(mutant, caught, None, caught)

    leg = mutant.case.leg_for(mutant.team)
    if leg is None:
        return Detection(mutant, False, None, False)
    caught = not permits(leg, season, base_cap)
    return Detection(
        mutant,
        caught,
        Code.NO_EXCEPTION_AVAILABLE if caught else None,
        caught and mutant.expected is Code.NO_EXCEPTION_AVAILABLE,
    )


def score(
    mutants: list[Mutant],
    real_cases: list[TradeCase],
    seasons: dict[str, Season],
    base_cap: int,
) -> Score:
    result = Score(real_cases=len(real_cases))
    for mutant in mutants:
        season = seasons.get(mutant.case.season_id)
        if season is None:
            continue
        result.detections.append(_detect(mutant, season, base_cap))

    # Real, legal trades the engine cannot permit under a simultaneous
    # exception. Counted against precision as the pessimistic reading.
    for case in real_cases:
        season = seasons.get(case.season_id)
        if season is None or not case.balanced:
            continue
        for leg in case.legs:
            if leg.incoming <= leg.outgoing or leg.outgoing <= 0:
                continue
            if not permits(leg, season, base_cap):
                result.undeterminable += 1
    return result
