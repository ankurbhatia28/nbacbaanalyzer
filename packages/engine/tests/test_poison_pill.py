"""
The two rules nicknamed "poison pill".

Both deem a salary to equal the average of a contract's remaining years, for one
party's Room only. The asymmetry is the whole point: an engine that values a
contract identically for both sides gets these backwards.
"""

import pytest

from engine.poison_pill import (
    ARENAS_BALLOON_CONDITIONS,
    CAP_GROWTH_ASSUMPTION,
    Party,
    arenas_applies,
    arenas_first_year_limit,
    arenas_fourth_year_bounds,
    arenas_offer_sheet_room_value,
    assumed_cap_for_extended_term,
    rookie_extension_trade_value,
)

EXTENDED = [30_000_000, 32_000_000, 34_000_000]
FINAL_ORIGINAL = 5_000_000


def test_the_acquiring_team_absorbs_the_average_not_the_actual():
    got = rookie_extension_trade_value(
        final_original_year_salary=FINAL_ORIGINAL,
        extended_term_salaries=EXTENDED,
        traded_before_extension_takes_effect=True,
        party=Party.ACQUIRING,
    )
    assert got.deemed
    assert got.amount == (FINAL_ORIGINAL + sum(EXTENDED)) // 4
    assert got.amount > FINAL_ORIGINAL * 4


def test_the_outgoing_team_uses_the_actual_salary():
    """The rule says "only for purposes of determining whether the acquiring Team has Room"."""
    got = rookie_extension_trade_value(
        final_original_year_salary=FINAL_ORIGINAL,
        extended_term_salaries=EXTENDED,
        traded_before_extension_takes_effect=True,
        party=Party.OUTGOING,
    )
    assert not got.deemed
    assert got.amount == FINAL_ORIGINAL


def test_the_two_sides_disagree_which_is_the_entire_mechanism():
    kw = dict(
        final_original_year_salary=FINAL_ORIGINAL,
        extended_term_salaries=EXTENDED,
        traded_before_extension_takes_effect=True,
    )
    acquiring = rookie_extension_trade_value(party=Party.ACQUIRING, **kw)
    outgoing = rookie_extension_trade_value(party=Party.OUTGOING, **kw)
    assert acquiring.amount != outgoing.amount


def test_the_rule_lapses_once_the_extension_takes_effect():
    got = rookie_extension_trade_value(
        final_original_year_salary=FINAL_ORIGINAL,
        extended_term_salaries=EXTENDED,
        traded_before_extension_takes_effect=False,
        party=Party.ACQUIRING,
    )
    assert not got.deemed
    assert got.amount == FINAL_ORIGINAL


def test_the_cap_growth_assumption_is_104_point_5_percent():
    assert CAP_GROWTH_ASSUMPTION == 1.045
    assert assumed_cap_for_extended_term(166_000_000) == 173_470_000


# -- Gilbert Arenas, Art. XI 5(d) -----------------------------------------


@pytest.mark.parametrize("yos,expected", [(0, False), (1, True), (2, True), (3, False)])
def test_arenas_applies_only_at_one_or_two_years_of_service(yos, expected):
    assert arenas_applies(yos) is expected


def test_the_first_year_is_capped_at_the_non_taxpayer_mle():
    """The cap on year one is what forces the third-year balloon."""
    assert arenas_first_year_limit(14_104_000) == 14_104_000


def test_the_offering_team_needs_room_for_the_average_not_year_one():
    sheet = [14_100_000, 14_800_000, 40_000_000, 41_800_000]
    got = arenas_offer_sheet_room_value(sheet)
    assert got.deemed
    assert got.amount == sum(sheet) // 4
    assert got.amount > sheet[0] * 1.9  # nearly double the first-year figure


def test_an_empty_offer_sheet_is_rejected():
    with pytest.raises(ValueError, match="at least one"):
        arenas_offer_sheet_room_value([])


def test_the_fourth_year_may_move_by_four_and_a_half_percent():
    low, high = arenas_fourth_year_bounds(40_000_000)
    assert low == 38_200_000
    assert high == 41_800_000


def test_the_balloon_carries_conditions_each_with_a_citation():
    assert len(ARENAS_BALLOON_CONDITIONS) == 3
    for text, citation in ARENAS_BALLOON_CONDITIONS:
        assert text and citation.article == "XI"
