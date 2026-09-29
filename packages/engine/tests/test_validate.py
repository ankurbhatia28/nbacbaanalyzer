"""validate_trade and team_trade_constraints."""

from datetime import date

from engine import Trade, TradeLeg, team_trade_constraints, validate_trade
from engine.fixtures import (
    SEASON_2026_27,
    capped_below_ceiling,
    first_apron_capped,
    room_team,
    second_apron_uncapped,
)
from engine.fixtures.contracts import fully_guaranteed, trade_kicker_unknown
from engine.violations import Code

S, BASE = SEASON_2026_27, 136_021_000
WHEN = date(2026, 12, 20)


def two_team(a, b, a_sends, a_gets):
    return Trade(
        season_id=S.season_id,
        as_of=WHEN,
        legs=[
            TradeLeg(team_id=a.team_id, sends=list(a_sends), receives=list(a_gets)),
            TradeLeg(team_id=b.team_id, sends=list(a_gets), receives=list(a_sends)),
        ],
    )


def test_a_balanced_swap_is_legal():
    a, b = room_team(), second_apron_uncapped()
    x, y = fully_guaranteed(S, 10_000_000), fully_guaranteed(S, 10_000_000)
    verdict = validate_trade(two_team(a, b, [x], [y]), {a.team_id: a, b.team_id: b}, BASE)
    assert verdict.legal, verdict.summary()


def test_taking_back_far_more_than_sent_is_refused_with_the_matching_citation():
    a, b = first_apron_capped(), room_team()
    verdict = validate_trade(
        two_team(a, b, [fully_guaranteed(S, 3_000_000)], [fully_guaranteed(S, 40_000_000)]),
        {a.team_id: a, b.team_id: b},
        BASE,
    )
    assert not verdict.legal
    codes = {v.code for v in verdict.violations}
    assert Code.NO_EXCEPTION_AVAILABLE in codes
    matching = next(v for v in verdict.violations if v.code is Code.NO_EXCEPTION_AVAILABLE)
    assert matching.citation.section.startswith("6(j)")


def test_exceeding_a_hard_cap_ceiling_names_the_transaction_that_set_it():
    """A verdict should say which past move created the ceiling, not just that one exists."""
    a, b = first_apron_capped(), room_team()
    verdict = validate_trade(
        two_team(a, b, [fully_guaranteed(S, 3_000_000)], [fully_guaranteed(S, 40_000_000)]),
        {a.team_id: a, b.team_id: b},
        BASE,
    )
    ceiling = next(v for v in verdict.violations if v.code is Code.HARD_CAP_CEILING_EXCEEDED)
    assert "row E" in ceiling.detail
    assert "first apron" in ceiling.detail


def test_each_team_is_validated_against_itself_not_the_netted_deal():
    """A deal balancing overall can still be illegal for one participant."""
    a, b = first_apron_capped(), room_team()
    verdict = validate_trade(
        two_team(a, b, [fully_guaranteed(S, 3_000_000)], [fully_guaranteed(S, 40_000_000)]),
        {a.team_id: a, b.team_id: b},
        BASE,
    )
    offenders = {v.team_id for v in verdict.violations}
    assert offenders == {a.team_id}  # the room team absorbing salary is fine


def test_an_unknown_trade_kicker_makes_the_verdict_conditional():
    """ADR-003: 'legal' and 'legal assuming no kicker' are different claims."""
    a, b = room_team(), second_apron_uncapped()
    unknown = trade_kicker_unknown(S)
    verdict = validate_trade(
        two_team(a, b, [fully_guaranteed(S, 21_000_000)], [unknown]),
        {a.team_id: a, b.team_id: b},
        BASE,
    )
    assert verdict.is_conditional
    assert any("trade_kicker" in x.field_name for x in verdict.assumptions)


def test_every_verdict_reports_which_checks_ran():
    """So 'legal' cannot be read as 'nothing else could be wrong'."""
    a, b = room_team(), second_apron_uncapped()
    verdict = validate_trade(
        two_team(a, b, [fully_guaranteed(S, 5_000_000)], [fully_guaranteed(S, 5_000_000)]),
        {a.team_id: a, b.team_id: b},
        BASE,
    )
    assert verdict.notes and "salary matching" in verdict.notes[0]


def test_missing_team_state_raises_rather_than_guessing():
    a, b = room_team(), second_apron_uncapped()
    trade = two_team(a, b, [fully_guaranteed(S, 1_000_000)], [fully_guaranteed(S, 1_000_000)])
    try:
        validate_trade(trade, {a.team_id: a}, BASE)
    except KeyError as e:
        assert b.team_id in str(e)
    else:
        raise AssertionError("should not validate a team it knows nothing about")


# -- constraint enumeration ------------------------------------------------


def test_constraints_report_a_ceiling_and_its_headroom():
    report = team_trade_constraints(capped_below_ceiling(), as_of=WHEN)
    ceiling = next(c for c in report.constraints if c.kind == "hard_cap")
    assert "second apron" in ceiling.detail
    assert "row K" in ceiling.detail
    assert not ceiling.blocking  # below it, so restricted but not stuck


def test_constraints_surface_a_superseded_ceiling_too():
    """Milwaukee holds two. The lower binds, but the other is still a fact."""
    report = team_trade_constraints(first_apron_capped(), as_of=WHEN)
    kinds = [c.kind for c in report.constraints]
    assert "hard_cap" in kinds
    assert "hard_cap_superseded" in kinds


def test_an_unconstrained_team_says_so_explicitly():
    report = team_trade_constraints(second_apron_uncapped(), as_of=WHEN)
    assert any("no hard-cap ceiling" in c.detail for c in report.constraints)
    assert not report.blocking


def test_naming_a_player_surfaces_an_unknown_trade_kicker():
    state = capped_below_ceiling()
    unknown = trade_kicker_unknown(S)
    state.contracts.append(unknown)
    report = team_trade_constraints(state, player_id=unknown.player_id, as_of=WHEN)
    assert any(c.kind == "unknown_trade_kicker" for c in report.constraints)
    assert report.assumptions


def test_naming_a_player_the_team_does_not_have_is_blocking():
    report = team_trade_constraints(room_team(), player_id="nobody", as_of=WHEN)
    assert any(c.kind == "unknown_player" and c.blocking for c in report.constraints)
