"""
Pick configurations, including one that is deliberately illegal.

Shapes taken from the 616 real protection strings: simple own pick (239),
swap rights (68), favourability ordering (49), range-protected (47), and
rollover-or-extinguish (32).
"""

from __future__ import annotations

from engine.picks import (
    ConveyanceOutcome,
    DraftPick,
    PickInventory,
    Protection,
    SwapRight,
)
from engine.provenance import Provenance, Source

FIXTURE = Provenance(Source.FIXTURE)


def own_outright(team_id: str = "FIX", year: int = 2027) -> DraftPick:
    return DraftPick(
        year=year,
        round_=1,
        original_team_id=team_id,
        current_owner_team_id=team_id,
        provenance=FIXTURE,
    )


def range_protected(team_id: str = "FIX", year: int = 2027) -> DraftPick:
    """ "protected for selections 1-4" -- the most common real shape."""
    return DraftPick(
        year=year,
        round_=1,
        original_team_id=team_id,
        current_owner_team_id="OTH",
        protections=(Protection(1, 4, ConveyanceOutcome.ROLL_FORWARD, rolls_to_year=year + 1),),
        raw_details="protected for selections 1-4; rolls forward if not conveyed",
        provenance=FIXTURE,
    )


def rollover_then_seconds(team_id: str = "FIX", year: int = 2027) -> DraftPick:
    """Top-20 protected, converting to seconds rather than rolling indefinitely."""
    return DraftPick(
        year=year,
        round_=1,
        original_team_id=team_id,
        current_owner_team_id="OTH",
        protections=(
            Protection(
                1,
                20,
                ConveyanceOutcome.CONVERT_TO_SECONDS,
                note="becomes a 2nd round pick if protected",
            ),
        ),
        raw_details="Top 20 protected. Becomes a 2nd round pick if protected.",
        provenance=FIXTURE,
    )


def swap_right(holder: str = "FIX", counterparty: str = "OTH", year: int = 2031) -> SwapRight:
    return SwapRight(
        holder_team_id=holder,
        counterparty_team_id=counterparty,
        year=year,
        round_=2,
        most_favorable=True,
        note="right to swap for the more favorable of the two",
    )


def forfeited_firsts(team_id: str = "LAC") -> PickInventory:
    """
    Mirrors the Clippers: firsts forfeited in five consecutive drafts,
    2029-2033, as a league penalty. Creates a Stepien interaction that no
    generic fixture would produce -- what does the consecutive-years rule permit
    when those years are already gone?
    """
    inv = PickInventory(team_id=team_id)
    for year in range(2027, 2034):
        inv.picks.append(
            DraftPick(
                year=year,
                round_=1,
                original_team_id=team_id,
                current_owner_team_id=team_id,
                forfeited=2029 <= year <= 2033,
                raw_details="forfeited by league penalty" if 2029 <= year <= 2033 else None,
                provenance=FIXTURE,
            )
        )
    return inv


def stepien_violating(team_id: str = "FIX") -> PickInventory:
    """
    NEGATIVE FIXTURE. Firsts traded away in consecutive future years, which the
    Stepien rule forbids. Phase 3 must reject this with the right violation
    code -- rejecting it for the wrong reason is still a failure.
    """
    inv = PickInventory(team_id=team_id)
    for year in (2027, 2029, 2031, 2033):
        inv.picks.append(own_outright(team_id, year))
    # 2028 and 2030 are gone: consecutive bare years once 2029 is also traded
    inv.picks.append(
        DraftPick(
            year=2029,
            round_=1,
            original_team_id=team_id,
            current_owner_team_id="OTH",
            provenance=FIXTURE,
        )
    )
    return inv


ALL_PICK_FIXTURES = (own_outright, range_protected, rollover_then_seconds)
