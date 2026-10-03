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


def test_a_team_sending_several_players_may_split_them_across_exceptions():
    """
    3.14a, which `validate_trade` did not use until the trade builder (7.4).

    Art. VII 6(j)(1)(i) lets one exception replace "one (1) Traded Player" and
    6(m) carves 6(j) out of its bar on combining exceptions, so four outgoing
    contracts may be matched as four. Judged as one aggregated exception this
    trade was refused, though a lawful structure permits it.
    """
    from engine.salary_matching import best_allowance, best_structure
    from engine.team_state import TeamState

    sent = [fully_guaranteed(S, x) for x in (20_000_000, 12_000_000, 9_435_741, 6_000_000)]
    filler = fully_guaranteed(S, 120_000_000)
    a = TeamState(team_id="A", season=S, contracts=[*sent, filler])
    outgoing = sum(c.cap_figure(S.season_id) for c in sent)
    structure = best_structure([c.cap_figure(S.season_id) for c in sent], S, 0, BASE)
    taken = fully_guaranteed(S, structure.total_allowance)
    post = a.apron_team_salary() - outgoing + structure.total_allowance
    assert post < S.first_apron
    # One exception alone does not permit it -- the case this test exists for.
    incoming = taken.cap_figure(S.season_id)
    assert best_allowance(outgoing, incoming, S, post, BASE, aggregating=True) is None

    b = TeamState(team_id="B", season=S, contracts=[taken, fully_guaranteed(S, 100_000_000)])
    verdict = validate_trade(two_team(a, b, sent, [taken]), {"A": a, "B": b}, BASE)
    assert verdict.legal, verdict.summary()
    assert any("exceptions" in note for note in verdict.notes)


def test_a_trade_matched_by_the_expanded_exception_says_it_hard_caps_the_team():
    """Art. VII 2(e)(2)(i)(B): legal, but at the cost of a first-apron ceiling (row E)."""
    from engine.team_state import TeamState

    a = TeamState(
        team_id="A",
        season=S,
        contracts=[fully_guaranteed(S, 20_000_000), fully_guaranteed(S, 150_000_000)],
    )
    b = TeamState(team_id="B", season=S, contracts=[fully_guaranteed(S, 100_000_000)])
    sent, taken = [a.contracts[0]], [fully_guaranteed(S, 28_000_000)]
    b.contracts.append(taken[0])
    verdict = validate_trade(two_team(a, b, sent, taken), {"A": a, "B": b}, BASE)
    assert verdict.legal, verdict.summary()
    assert any("row E" in n and "first apron" in n for n in verdict.notes), verdict.notes


def test_an_exception_in_the_restrictions_table_is_barred_above_its_apron():
    """
    Art. VII 2(e)(2)(i)(A): a team may not use the Expanded exception (row E)
    if its Apron Team Salary would exceed the first apron immediately after.
    The amount 6(j)(1)(iv) permits is irrelevant once the transaction is barred.
    Found by the trade builder (7.4): Murray for Irving and Washington was
    called legal while leaving Denver over the second apron.
    """
    from engine.team_state import TeamState

    a = TeamState(
        team_id="A",
        season=S,
        contracts=[fully_guaranteed(S, 20_000_000), fully_guaranteed(S, 190_000_000)],
    )
    b = TeamState(team_id="B", season=S, contracts=[fully_guaranteed(S, 100_000_000)])
    sent, taken = [a.contracts[0]], [fully_guaranteed(S, 28_000_000)]
    b.contracts.append(taken[0])
    assert a.apron_team_salary() - 20_000_000 + 28_000_000 > S.first_apron
    verdict = validate_trade(two_team(a, b, sent, taken), {"A": a, "B": b}, BASE)
    assert not verdict.legal
    (barred,) = [v for v in verdict.violations if v.team_id == "A"]
    assert barred.code is Code.APRON_TRANSACTION_BARRED
    assert barred.citation.section == "2(e)(2)(i)(A)"
    assert "expanded" in barred.detail
