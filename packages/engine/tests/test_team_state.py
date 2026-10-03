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


def test_denver_holds_count_against_the_cap_but_not_the_aprons():
    """
    The worked case, corrected in Phase 7. $208.7M of active salary plus $41.9M
    of free-agent holds is $250.6M of cap salary -- but Art. VII §2(e)(1)(iv)
    subtracts Free Agent Amounts from Apron Team Salary, so Denver is a
    taxpayer below the first apron, not a second-apron team.

    This test used to assert SECOND_APRON. The engine counted holds toward the
    aprons, and the test encoded the same mistake.
    """
    den = TeamState(
        team_id="DEN",
        season=SEASON,
        contracts=[contract("p1", 208_710_566)],
        cap_holds=[CapHold(HoldKind.FREE_AGENT, 41_870_144)],
    )
    assert den.committed_salary() == 208_710_566
    assert den.cap_salary() == 250_580_710
    assert den.apron_team_salary() == 208_710_566
    assert den.apron_status() is ApronStatus.TAXPAYER


def test_a_restricted_free_agent_counts_toward_the_aprons_at_the_qualifying_offer():
    """§2(e)(1)(iv) removes the hold; (v) adds back the outstanding Qualifying Offer."""
    den = TeamState(
        team_id="DEN",
        season=SEASON,
        contracts=[contract("p1", 200_000_000)],
        cap_holds=[CapHold(HoldKind.QUALIFYING_OFFER, 13_069_428, qualifying_offer=6_534_714)],
    )
    assert den.cap_salary() == 213_069_428
    assert den.apron_team_salary() == 206_534_714


def test_draft_and_incomplete_roster_holds_are_excluded_from_the_aprons():
    """§2(e)(1)(vi) and (x)."""
    team = TeamState(
        team_id="X",
        season=SEASON,
        contracts=[contract("p1", 150_000_000)],
        cap_holds=[
            CapHold(HoldKind.DRAFT_PICK, 3_173_040),
            CapHold(HoldKind.INCOMPLETE_ROSTER, 1_272_870),
        ],
    )
    assert team.apron_team_salary() == 150_000_000


def test_room_is_a_cap_question_so_holds_can_take_it_away():
    """
    Holds are excluded from the aprons, not from the cap. A team whose contracts
    sit under the cap but whose holds take it over has no room.
    """
    team = TeamState(
        team_id="X",
        season=SEASON,
        contracts=[contract("p1", 150_000_000)],
        cap_holds=[CapHold(HoldKind.FREE_AGENT, 20_000_000)],
    )
    assert team.apron_team_salary() < SEASON.salary_cap < team.cap_salary()
    assert team.apron_status() is ApronStatus.OVER_CAP


def test_no_ceiling_means_no_room_figure():
    den = TeamState(team_id="DEN", season=SEASON, contracts=[contract("p1", 1_000_000)])
    assert den.effective_ceiling() is None
    assert den.room_below_ceiling() is None


def test_minimum_scale_clamps_above_the_published_top():
    assert SEASON.minimum_for(0) == 1_272_870
    assert SEASON.minimum_for(25) == SEASON.minimum_for(10)
