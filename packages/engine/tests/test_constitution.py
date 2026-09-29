"""NBA Constitution and By-Laws rules -- a different document from the CBA."""

from datetime import date

import pytest

from engine.constitution import (
    ALL_BY_LAWS,
    FIRST_ROUND_DRAFT_CHOICE,
    check_first_round_rule,
    consecutive_bare_years,
    deadline_for,
    may_sell_first_round_pick_for_cash,
    trading_window,
)

YEARS = range(2027, 2034)


def holds(*bare: int) -> dict[int, bool]:
    return {y: y not in bare for y in YEARS}


def test_by_laws_render_as_a_distinct_document():
    """A verdict must not imply the CBA prohibits something the By-Laws do."""
    assert "Constitution and By-Laws" in str(FIRST_ROUND_DRAFT_CHOICE)
    assert FIRST_ROUND_DRAFT_CHOICE.short == "By-Law 7.03"
    for by_law in ALL_BY_LAWS:
        assert by_law.section and by_law.title and 1 <= by_law.page <= 88


def test_alternating_bare_years_are_permitted():
    """The Clippers' real shape: bare in 2028, 2030, 2032 -- never consecutive."""
    got = check_first_round_rule(years_examined=YEARS, holds_first_in=holds(2028, 2030, 2032))
    assert got.permitted
    assert got.bare_years == (2028, 2030, 2032)


def test_two_consecutive_bare_years_are_barred():
    got = check_first_round_rule(years_examined=YEARS, holds_first_in=holds(2028, 2029))
    assert not got.permitted
    assert got.consecutive_pair == (2028, 2029)
    assert got.by_law is FIRST_ROUND_DRAFT_CHOICE


def test_any_first_round_pick_satisfies_the_rule_not_just_your_own():
    """
    7.03 says "without first-round picks", so another team's first counts. The
    Clippers hold Toronto firsts in 2031 and 2033; treating those years as bare
    would make a legal position look illegal.
    """
    got = check_first_round_rule(years_examined=YEARS, holds_first_in=holds(2030, 2032))
    assert got.permitted


def test_a_pick_that_might_not_convey_counts_as_possibly_lost():
    """
    The text bars a trade whose result "may be" to leave the Member bare, so a
    protected pick that might not convey has to be treated as absent.
    """
    optimistic = check_first_round_rule(years_examined=YEARS, holds_first_in=holds(2028))
    assert optimistic.permitted

    cautious = check_first_round_rule(
        years_examined=YEARS, holds_first_in=holds(2028), years_possibly_lost={2029}
    )
    assert not cautious.permitted
    assert cautious.consecutive_pair == (2028, 2029)


def test_selling_a_first_round_pick_for_cash_is_barred_outright():
    """
    Distinct from the CBA's row I, which permits paying cash in a trade at the
    price of a second-apron ceiling. Selling a first for cash is barred by
    league rule regardless.
    """
    assert may_sell_first_round_pick_for_cash() is False


@pytest.mark.parametrize(
    "all_star,expected",
    [
        (date(2027, 2, 15), date(2027, 2, 4)),  # Monday game
        (date(2027, 2, 14), date(2027, 2, 4)),  # Sunday game, same week
    ],
)
def test_deadline_is_the_second_thursday_before_the_all_star_game(all_star, expected):
    assert deadline_for(all_star) == expected


def test_trading_is_closed_between_the_deadline_and_the_season_ending():
    args = dict(all_star_game=date(2027, 2, 14), last_regular_season_game=date(2027, 4, 12))
    assert trading_window(when=date(2027, 1, 20), **args).open_
    assert not trading_window(when=date(2027, 3, 1), **args).open_
    assert trading_window(when=date(2027, 4, 13), **args).open_


def test_the_moratorium_closes_the_window_regardless():
    assert not trading_window(
        when=date(2027, 7, 3),
        all_star_game=date(2027, 2, 14),
        last_regular_season_game=date(2027, 4, 12),
        in_moratorium=True,
    ).open_


def test_a_postseason_team_may_not_move_a_rostered_player():
    assert not trading_window(
        when=date(2027, 5, 1),
        all_star_game=date(2027, 2, 14),
        last_regular_season_game=date(2027, 4, 12),
        player_on_postseason_roster_of_active_team=True,
    ).open_


def test_no_consecutive_pair_in_an_empty_set():
    assert consecutive_bare_years(set()) is None
