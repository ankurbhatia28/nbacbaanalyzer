"""
Team shells, one per apron situation.

A single fifteen-man roster cannot hold five apron classifications, and apron
status changes *which rules apply at all*. Each shell mirrors a real 2026-27
team so its verdicts are checkable by someone who follows the league.
"""

from __future__ import annotations

from datetime import date

from engine.apron import ApronLevel, CeilingSet, HardCapCeiling, RestrictionRow
from engine.contract import Contract, ContractType, ContractYear
from engine.holds import BirdRights, CapHold, DeadMoney, HoldKind
from engine.maybe import Maybe
from engine.provenance import Provenance, Source
from engine.roster import RosterState
from engine.season import Season
from engine.team_state import TeamState

from .picks import forfeited_firsts
from .season import SEASON_2026_27

FIXTURE = Provenance(Source.FIXTURE)


def _filler(team_id: str, season: Season, total: int, n: int = 12) -> list[Contract]:
    """n contracts summing to `total`, so shells hit a target salary exactly."""
    each, remainder = divmod(total, n)
    out = []
    for i in range(n):
        amount = each + (remainder if i == 0 else 0)
        out.append(
            Contract(
                player_id=f"{team_id}_p{i}",
                team_id=team_id,
                contract_type=ContractType.VETERAN,
                years=(ContractYear(season.season_id, amount),),
                trade_kicker_pct=Maybe.absent(),
                no_trade_clause=Maybe.absent(),
                provenance=FIXTURE,
            )
        )
    return out


def room_team(season: Season = SEASON_2026_27) -> TeamState:
    """
    Brooklyn: committed salary sits under the cap, but cap holds push cap salary
    over it. A team has room only after renouncing its holds -- so "under the
    cap" in press coverage almost always means committed salary, not cap salary.
    That gap is the point of this shell.
    """
    return TeamState(
        team_id="ROOM",
        season=season,
        contracts=_filler("ROOM", season, 160_324_651, 15),
        cap_holds=[CapHold(HoldKind.FREE_AGENT, 10_007_415, bird_rights=BirdRights.NON)],
        roster=RosterState(standard_count=15),
        provenance=FIXTURE,
    )


def first_apron_capped(season: Season = SEASON_2026_27) -> TeamState:
    """
    Milwaukee: holds TWO ceilings. Paying cash on Jun 24 set one at the second
    apron (row I); acquiring Caris LeVert with an Expanded TPE on Jul 8 set one
    at the first (row E). The lower binds, which is why ceilings are a set.
    """
    ceilings = CeilingSet()
    ceilings.add(
        HardCapCeiling(
            RestrictionRow.I_CASH_PAID,
            ApronLevel.SECOND,
            date(season.start_year, 6, 24),
            season.season_id,
            "cash paid to ORL",
        )
    )
    ceilings.add(
        HardCapCeiling(
            RestrictionRow.E_EXPANDED_TPE,
            ApronLevel.FIRST,
            date(season.start_year, 7, 8),
            season.season_id,
            "Caris LeVert via expanded TPE",
        )
    )
    return TeamState(
        team_id="CAP1",
        season=season,
        contracts=_filler("CAP1", season, 183_997_778, 14),
        dead_money=[DeadMoney(23_183_270, description="fixture dead cap")],
        ceilings=ceilings,
        roster=RosterState(standard_count=14),
        provenance=FIXTURE,
    )


def capped_below_ceiling(season: Season = SEASON_2026_27) -> TeamState:
    """
    Houston: well BELOW the second apron yet forbidden from crossing it, having
    signed with the Taxpayer MLE (row K). The case that forces apron status and
    apron ceiling to be separate fields.
    """
    ceilings = CeilingSet()
    ceilings.add(
        HardCapCeiling(
            RestrictionRow.K_TAXPAYER_MLE,
            ApronLevel.SECOND,
            date(season.start_year, 7, 10),
            season.season_id,
            "Taxpayer MLE signing",
        )
    )
    return TeamState(
        team_id="CAP2",
        season=season,
        contracts=_filler("CAP2", season, 194_157_318, 13),
        ceilings=ceilings,
        roster=RosterState(standard_count=13),
        provenance=FIXTURE,
    )


def second_apron_uncapped(season: Season = SEASON_2026_27) -> TeamState:
    """
    Oklahoma City: ABOVE the second apron and free to go higher, with no
    ceiling at all. The exact inverse of Houston.
    """
    return TeamState(
        team_id="APR2",
        season=season,
        contracts=_filler("APR2", season, 232_001_714, 15),
        cap_holds=[CapHold(HoldKind.FREE_AGENT, 2_185_116, bird_rights=BirdRights.EARLY)],
        roster=RosterState(standard_count=15),
        provenance=FIXTURE,
    )


def holds_divergence(season: Season = SEASON_2026_27) -> TeamState:
    """
    Denver: committed salary sits UNDER the second apron, cap salary sits well
    OVER it. Which of the three totals you use decides the answer, which is the
    whole reason task 3.2 computes three.
    """
    return TeamState(
        team_id="DIVG",
        season=season,
        contracts=_filler("DIVG", season, 208_710_566, 11),
        cap_holds=[
            CapHold(HoldKind.FREE_AGENT, 34_975_962, bird_rights=BirdRights.FULL),
            CapHold(HoldKind.FREE_AGENT, 6_894_182, bird_rights=BirdRights.NON),
        ],
        dead_money=[DeadMoney(2_000_000)],
        roster=RosterState(standard_count=11),
        provenance=FIXTURE,
    )


def pick_poverty(season: Season = SEASON_2026_27) -> TeamState:
    """The Clippers: firsts forfeited across 2029-2033 by league penalty."""
    return TeamState(
        team_id="NOPX",
        season=season,
        contracts=_filler("NOPX", season, 193_693_925, 13),
        picks=forfeited_firsts("NOPX"),
        roster=RosterState(standard_count=13),
        provenance=FIXTURE,
    )


ALL_SHELLS = (
    room_team,
    first_apron_capped,
    capped_below_ceiling,
    second_apron_uncapped,
    holds_divergence,
    pick_poverty,
)
