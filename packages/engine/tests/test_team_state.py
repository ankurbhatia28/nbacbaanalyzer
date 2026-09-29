"""The three salary totals diverge, and the divergence changes the answer."""

from engine import ApronStatus, CapHold, HoldKind, Season, TeamState
from engine.contract import Contract, ContractType, ContractYear

SEASON = Season(
    season_id="2026-2027",
    salary_cap=166_000_000,
    tax_level=201_690_000,
    first_apron=210_690_000,
    second_apron=223_690_000,
    non_taxpayer_mle=14_100_000,
    taxpayer_mle=5_700_000,
    room_mle=8_700_000,
    bi_annual_exception=5_200_000,
    minimum_scale={0: 1_272_870, 1: 2_048_494, 10: 3_800_000},
)


def contract(pid, amount):
    return Contract(
        player_id=pid,
        team_id="DEN",
        contract_type=ContractType.VETERAN,
        years=(ContractYear("2026-2027", amount),),
    )


def test_denver_crosses_the_second_apron_only_once_holds_count():
    """
    The worked case. $208.7M of active salary sits under the second apron;
    $250.6M with holds sits well over it. Which number you use decides whether
    Denver is a second-apron team.
    """
    den = TeamState(
        team_id="DEN",
        season=SEASON,
        contracts=[contract("p1", 208_710_566)],
        cap_holds=[CapHold(HoldKind.FREE_AGENT, 41_870_144)],
    )
    assert den.committed_salary() == 208_710_566
    assert den.cap_salary() == 250_580_710
    assert den.committed_salary() < SEASON.second_apron
    assert den.cap_salary() > SEASON.second_apron
    assert den.apron_status() is ApronStatus.SECOND_APRON


def test_no_ceiling_means_no_room_figure():
    den = TeamState(team_id="DEN", season=SEASON, contracts=[contract("p1", 1_000_000)])
    assert den.effective_ceiling() is None
    assert den.room_below_ceiling() is None


def test_minimum_scale_clamps_above_the_published_top():
    assert SEASON.minimum_for(0) == 1_272_870
    assert SEASON.minimum_for(25) == SEASON.minimum_for(10)
