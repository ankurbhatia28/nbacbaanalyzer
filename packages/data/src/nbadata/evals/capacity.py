"""
How much incoming salary a leg may absorb, in one place.

The mutation generator, the scorer and the harness all need this, and they must
agree. When they disagreed the suite quietly lost its meaning: `just_over_the_band`
set incoming one dollar above the largest *single* exception, but a team sending
several players may split them across several exceptions (Art. VII 6(j)(1)(i),
carved out of 6(m)), so that dollar was often still legal. Those mutants were
counted as caught while not actually being illegal, which inflates recall.
"""

from __future__ import annotations

from engine.salary_matching import aggregated, best_structure, expanded, standard
from engine.season import Season

from .corpus import Leg


def ceiling(leg: Leg, season: Season, base_cap: int) -> int:
    """
    The largest incoming salary any lawful structure permits against this leg.

    Where the individual outgoing contracts are known, the team may split them
    across exceptions, which permits materially more. Where they are not, the
    best a single exception offers is the most that can be claimed.
    """
    if leg.outgoing_reconstructed:
        return best_structure(list(leg.outgoing_salaries), season, 0, base_cap).total_allowance
    return max(
        standard(leg.outgoing, season, 0).amount,
        aggregated(leg.outgoing, season, 0).amount,
        expanded(leg.outgoing, season, 0, base_cap).amount,
    )


def permits(leg: Leg, season: Season, base_cap: int) -> bool:
    """Whether a simultaneous trade exception can absorb what this leg takes in."""
    if leg.outgoing <= 0:
        return False
    return leg.incoming <= ceiling(leg, season, base_cap)
