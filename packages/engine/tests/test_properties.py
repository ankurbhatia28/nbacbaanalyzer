"""
Property-based tests (task 3.21).

Worked examples check the cases the drafters thought to write down. These check
invariants that must hold across the whole input space -- the kind of thing that
breaks on a boundary nobody enumerated.
"""

from dataclasses import replace

from hypothesis import assume, given
from hypothesis import strategies as st

from engine.apron import (
    ApronLevel,
    CeilingSet,
    HardCapCeiling,
    RestrictionRow,
    SeasonThresholds,
)
from engine.apron_restrictions import may_engage
from engine.constitution import check_first_round_rule, consecutive_bare_years
from engine.fixtures import SEASON_2026_27 as S
from engine.maybe import AssumptionLog, Maybe
from engine.salary_matching import best_allowance, expanded, standard

BASE_CAP = 136_021_000
money = st.integers(min_value=0, max_value=500_000_000)
salary = st.integers(min_value=1, max_value=100_000_000)
NON_EXEMPT = [r for r in RestrictionRow if r.is_reachable_after_2024]
THRESHOLDS = SeasonThresholds(S.first_apron, S.second_apron)


@given(row=st.sampled_from(NON_EXEMPT), lower=money, delta=money)
def test_permission_is_monotonic_in_salary(row, lower, delta):
    """If a transaction is allowed at some salary, it is allowed at any lower one."""
    higher = lower + delta
    if may_engage(row, apron_salary_after=higher, season=S).permitted:
        assert may_engage(row, apron_salary_after=lower, season=S).permitted


@given(row=st.sampled_from(NON_EXEMPT), amount=st.integers(min_value=0, max_value=166_000_000))
def test_a_team_below_both_aprons_is_never_barred(row, amount):
    assert may_engage(row, apron_salary_after=amount, season=S).permitted


@given(outgoing=salary, post=money)
def test_expanded_is_never_worse_than_standard(outgoing, post):
    """
    The expanded exception exists to permit more. If it ever allowed less, a
    team would be taking on an apron ceiling for nothing.
    """
    assert expanded(outgoing, S, post, BASE_CAP).amount >= standard(outgoing, S, post).amount


@given(outgoing=salary, incoming=salary, post=money, aggregating=st.booleans())
def test_a_returned_allowance_always_permits_the_trade(outgoing, incoming, post, aggregating):
    """best_allowance must never hand back an exception that does not fit."""
    got = best_allowance(outgoing, incoming, S, post, BASE_CAP, aggregating=aggregating)
    if got is not None:
        assert got.permits(incoming)


@given(outgoing=salary, post=money)
def test_no_allowance_is_ever_negative(outgoing, post):
    for got in (standard(outgoing, S, post), expanded(outgoing, S, post, BASE_CAP)):
        assert got.amount >= 0


@given(levels=st.lists(st.sampled_from(list(ApronLevel)), min_size=1, max_size=6))
def test_the_binding_ceiling_is_always_the_lowest(levels):
    """Milwaukee's case generalised: more ceilings can only tighten, never loosen."""
    from datetime import date

    ceilings = CeilingSet()
    for i, level in enumerate(levels):
        ceilings.add(
            HardCapCeiling(
                RestrictionRow.I_CASH_PAID
                if level is ApronLevel.SECOND
                else RestrictionRow.E_EXPANDED_TPE,
                level,
                date(2026, 7, 1 + i % 28),
                S.season_id,
            )
        )
    level, amount = ceilings.effective(THRESHOLDS)
    assert amount == min(THRESHOLDS.amount_for(x) for x in levels)
    assert level is (ApronLevel.FIRST if ApronLevel.FIRST in levels else ApronLevel.SECOND)


@given(years=st.sets(st.integers(min_value=2027, max_value=2040), max_size=10))
def test_stepien_is_exactly_the_absence_of_a_consecutive_bare_pair(years):
    """The rule reduces to one predicate, so the two must never disagree."""
    span = range(2027, 2041)
    holds = {y: y not in years for y in span}
    got = check_first_round_rule(years_examined=span, holds_first_in=holds)
    assert got.permitted == (consecutive_bare_years(years) is None)


@given(
    years=st.sets(st.integers(min_value=2027, max_value=2040), max_size=8),
    extra=st.sets(st.integers(min_value=2027, max_value=2040), max_size=4),
)
def test_losing_more_picks_never_makes_stepien_pass(years, extra):
    span = range(2027, 2041)
    before = check_first_round_rule(
        years_examined=span, holds_first_in={y: y not in years for y in span}
    )
    after = check_first_round_rule(
        years_examined=span, holds_first_in={y: y not in (years | extra) for y in span}
    )
    if not before.permitted:
        assert not after.permitted


@given(default=st.integers(), known=st.integers())
def test_a_known_value_is_returned_unchanged_and_records_nothing(default, known):
    log = AssumptionLog()
    assert log.read(Maybe.known(known), default, "x", "f", "r") == known
    assert log.is_empty


@given(default=st.integers())
def test_an_unknown_value_always_records_exactly_one_assumption(default):
    log = AssumptionLog()
    assert log.read(Maybe.unknown(), default, "x", "f", "r") == default
    assert len(log) == 1


@given(
    cap=st.integers(min_value=100_000_000, max_value=300_000_000),
    gap=st.integers(min_value=1, max_value=50_000_000),
)
def test_the_allowance_vanishes_above_the_first_apron_and_not_below(cap, gap):
    season = replace(S, first_apron=cap, second_apron=cap + gap)
    assume(cap > 1)
    assert standard(1_000_000, season, cap).allowance_applied > 0
    assert standard(1_000_000, season, cap + 1).allowance_applied == 0
