"""
The mutation suite.

Real trades only catch the engine refusing something legal. Mutants catch it
permitting something illegal, which is the direction that matters more for a
system whose answers people act on.
"""

import pytest

from engine.fixtures import SEASON_2026_27 as S
from engine.salary_matching import best_allowance
from engine.violations import Code
from nbadata.evals.corpus import Leg, TradeCase
from nbadata.evals.mutate import (
    MutationKind,
    generate,
    inflate_incoming,
    just_over_the_band,
    unbalance,
)
from nbadata.evals.score import score

BASE = 136_021_000
SEASONS = {"2026-2027": S}


def case(*legs):
    c = TradeCase(trade_id=99, date="2026-07-01")
    c.legs = list(legs)
    return c


LEGAL = case(
    Leg("MIL", 10_000_000, 10_000_000, 0, 0, False, 1),
    Leg("BOS", 10_000_000, 10_000_000, 0, 0, False, 1),
)


def test_an_inflated_trade_becomes_genuinely_illegal():
    mutants = inflate_incoming(LEGAL, S, BASE)
    assert mutants
    for m in mutants:
        leg = m.case.leg_for(m.team)
        assert best_allowance(leg.outgoing, leg.incoming, S, 0, BASE, aggregating=True) is None
        assert m.expected is Code.NO_EXCEPTION_AVAILABLE


def test_the_boundary_mutation_sits_exactly_one_dollar_over():
    """
    An off-by-$250,000 error from mishandling the allowance survives a blunt
    4x mutation and dies here. That is the whole reason this generator exists.
    """
    mutants = just_over_the_band(LEGAL, S, BASE)
    assert mutants
    for m in mutants:
        leg = m.case.leg_for(m.team)
        permitted = best_allowance(leg.outgoing, leg.incoming - 1, S, 0, BASE, aggregating=True)
        assert permitted is not None, "one dollar lower must still be legal"
        assert permitted.amount == leg.incoming - 1
        assert best_allowance(leg.outgoing, leg.incoming, S, 0, BASE, aggregating=True) is None


def test_unbalancing_breaks_the_corpus_invariant():
    mutants = unbalance(LEGAL, S, BASE)
    assert mutants
    assert not mutants[0].case.balanced
    assert mutants[0].expected is None  # caught by the harness, not a rule


def test_undeterminable_legs_are_never_mutated():
    """
    A leg already relying on cap room or a standing exception cannot be
    evaluated, so breaking it proves nothing either way.
    """
    undetermined = case(Leg("MIL", 30_000_000, 0, 0, 0, False, 1))
    assert inflate_incoming(undetermined, S, BASE) == []
    assert just_over_the_band(undetermined, S, BASE) == []


def test_generation_covers_every_kind():
    mutants = generate([LEGAL], SEASONS, BASE)
    assert {m.kind for m in mutants} == set(MutationKind)


def test_every_mutant_records_its_source_and_reason():
    for m in generate([LEGAL], SEASONS, BASE):
        assert m.source_trade_id == LEGAL.trade_id
        assert m.note and m.team


# -- scoring ---------------------------------------------------------------


def test_perfect_detection_scores_full_recall():
    result = score(generate([LEGAL], SEASONS, BASE), [LEGAL], SEASONS, BASE)
    assert result.recall == 1.0
    assert result.reason_accuracy == 1.0


def test_precision_is_reported_as_a_floor_not_a_measurement():
    """
    Its denominator counts real trades the engine cannot permit outright, most
    of which are cap room rather than errors. Claiming that as measured
    precision would overstate what the corpus can show.
    """
    undetermined = case(Leg("MIL", 30_000_000, 5_000_000, 0, 0, False, 1))
    result = score([], [undetermined], SEASONS, BASE)
    assert result.undeterminable == 1
    assert hasattr(result, "precision_floor")
    assert not hasattr(result, "precision")


def test_an_engine_that_catches_nothing_scores_zero_recall():
    result = score([], [LEGAL], SEASONS, BASE)
    assert result.recall == 0.0


@pytest.mark.parametrize("season_id", ["1999-2000"])
def test_mutants_in_unknown_seasons_are_not_scored(season_id):
    orphan = TradeCase(trade_id=1, date="1999-08-01")
    orphan.legs = [Leg("MIL", 10_000_000, 1_000_000, 0, 0, False, 1)]
    result = score(generate([orphan], SEASONS, BASE), [], SEASONS, BASE)
    assert result.detections == []
