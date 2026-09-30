"""
Mutation testing (task 4.5).

Real trades are all legal, so the corpus only ever catches the engine saying no
when it should say yes. The other direction -- the engine saying yes when it
should say no -- needs cases that are illegal in a *known* way, and those have to
be manufactured.

Each mutation takes a real, legal trade and breaks it in one specific respect,
carrying the violation it must now produce. Two properties make that a stronger
test than hand-written illegal cases:

* the starting point is real, so the mutation is a small edit to something the
  league actually did rather than a scenario invented to suit the engine;
* the expected violation is known, so rejecting for the *wrong* reason is a
  failure. An engine that refuses everything scores zero, not perfect.

A mutation whose base case the engine could not conclusively evaluate is
discarded rather than counted, because breaking an undetermined case tells you
nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from engine.salary_matching import aggregated, best_allowance, expanded, standard
from engine.season import Season
from engine.violations import Code

from .corpus import Leg, TradeCase


class MutationKind(StrEnum):
    INFLATE_INCOMING = "inflate_incoming"
    JUST_OVER_THE_BAND = "just_over_the_band"
    UNBALANCE = "unbalance"


@dataclass(frozen=True, slots=True)
class Mutant:
    kind: MutationKind
    expected: Code | None
    case: TradeCase
    team: str
    note: str
    source_trade_id: int


def _replace_leg(case: TradeCase, team: str, new_leg: Leg) -> TradeCase:
    mutated = TradeCase(trade_id=case.trade_id, date=case.date, balanced=case.balanced)
    mutated.legs = [new_leg if leg.team == team else leg for leg in case.legs]
    return mutated


def _conclusively_legal(leg: Leg, season: Season, base_cap: int) -> bool:
    """
    Only mutate a leg the engine can currently evaluate. A leg that already
    needs cap room or a standing exception is undetermined, and breaking an
    undetermined case proves nothing either way.
    """
    if leg.outgoing <= 0:
        return False
    if leg.incoming <= leg.outgoing:
        return True
    return (
        best_allowance(leg.outgoing, leg.incoming, season, 0, base_cap, aggregating=True)
        is not None
    )


def inflate_incoming(
    case: TradeCase, season: Season, base_cap: int, *, factor: int = 4
) -> list[Mutant]:
    """
    Push incoming salary past every exception in Art. VII 6(j).

    The multiplier is deliberately large. A marginal overshoot could be absorbed
    by the $250,000 allowance or by a different exception, which would make the
    expected violation a guess rather than a certainty.
    """
    out: list[Mutant] = []
    for leg in case.legs:
        if not _conclusively_legal(leg, season, base_cap):
            continue
        inflated = replace(leg, incoming=max(leg.incoming, leg.outgoing) * factor + 10_000_000)
        if (
            best_allowance(
                inflated.outgoing, inflated.incoming, season, 0, base_cap, aggregating=True
            )
            is not None
        ):
            continue  # still permitted, so not a valid mutation
        out.append(
            Mutant(
                MutationKind.INFLATE_INCOMING,
                Code.NO_EXCEPTION_AVAILABLE,
                _replace_leg(case, leg.team, inflated),
                leg.team,
                f"incoming raised from ${leg.incoming:,} to ${inflated.incoming:,} "
                f"against ${leg.outgoing:,} sent",
                case.trade_id,
            )
        )
    return out


def unbalance(case: TradeCase, season: Season, base_cap: int) -> list[Mutant]:
    """
    Break the corpus invariant itself, so the harness is tested as well as the
    engine. A mutated case whose figures no longer add up must be caught before
    any rule is applied to it.
    """
    for leg in case.legs:
        if leg.incoming <= 0:
            continue
        mutated = _replace_leg(case, leg.team, replace(leg, incoming=leg.incoming + 7_777_777))
        mutated.balanced = False
        return [
            Mutant(
                MutationKind.UNBALANCE,
                None,
                mutated,
                leg.team,
                "incoming altered so the trade no longer balances",
                case.trade_id,
            )
        ]
    return []


def just_over_the_band(case: TradeCase, season: Season, base_cap: int) -> list[Mutant]:
    """
    Raise incoming to one dollar above the largest allowance that fits.

    The blunt 4x mutation is caught by any engine that computes anything at all.
    This one is caught only by an engine that computes the boundary *correctly*,
    which is the claim worth testing -- an off-by-$250,000 error from mishandling
    the allowance passes the blunt test and fails this one.
    """
    out: list[Mutant] = []
    for leg in case.legs:
        if not _conclusively_legal(leg, season, base_cap):
            continue
        # best_allowance returns the *least* consequential exception that fits,
        # which is not the boundary. The largest allowance any exception offers
        # is what a trade actually has to clear, so that is what we step over.
        largest = max(
            (
                standard(leg.outgoing, season, 0).amount,
                aggregated(leg.outgoing, season, 0).amount,
                expanded(leg.outgoing, season, 0, base_cap).amount,
            )
        )
        over = replace(leg, incoming=largest + 1)
        if (
            best_allowance(over.outgoing, over.incoming, season, 0, base_cap, aggregating=True)
            is not None
        ):
            continue
        out.append(
            Mutant(
                MutationKind.JUST_OVER_THE_BAND,
                Code.NO_EXCEPTION_AVAILABLE,
                _replace_leg(case, leg.team, over),
                leg.team,
                f"incoming set to ${over.incoming:,}, one dollar above the largest "
                f"allowance any exception offers on ${leg.outgoing:,} sent (${largest:,})",
                case.trade_id,
            )
        )
    return out


GENERATORS = (inflate_incoming, just_over_the_band, unbalance)


def generate(cases: list[TradeCase], seasons: dict[str, Season], base_cap: int) -> list[Mutant]:
    mutants: list[Mutant] = []
    for case in cases:
        season = seasons.get(case.season_id)
        if season is None or not case.balanced:
            continue
        for generator in GENERATORS:
            mutants.extend(generator(case, season, base_cap))
    return mutants
