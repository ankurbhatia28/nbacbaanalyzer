"""
Salary matching, Article VII Section 6(j).

The headline assertion is that this is NOT "125% + $100,000". That figure is the
2017 CBA, is what most secondary sources still print, and would make every
matching verdict wrong in a way no test would catch unless one asserts it.
"""

from dataclasses import replace

import pytest

from engine.fixtures import SEASON_2026_27
from engine.salary_matching import (
    ALLOWANCE,
    MatchingExceptionKind,
    aggregated,
    allowance_cushion,
    best_allowance,
    expanded,
    room,
    standard,
    transition,
)

S = SEASON_2026_27
BASE_CAP = 136_021_000  # 2023-24 salary cap, the Expanded exception's denominator
UNDER = 150_000_000  # a post-assignment apron salary below the first apron


def test_standard_band_is_one_hundred_percent_plus_250k_not_125_plus_100k():
    got = standard(10_000_000, S, UNDER)
    assert got.amount == 10_250_000
    assert got.amount != 12_600_000  # the 2017 figure, still widely cited


def test_allowance_is_250k_not_100k():
    assert ALLOWANCE == 250_000


def test_aggregated_matches_the_standard_band():
    assert aggregated(10_000_000, S, UNDER).amount == standard(10_000_000, S, UNDER).amount


def test_transition_exists_only_in_2023_24():
    assert transition(10_000_000, S, UNDER) is None
    old = replace(S, season_id="2023-2024")
    got = transition(10_000_000, old, UNDER)
    assert got is not None
    assert got.amount == 11_250_000  # 110% + 250k


def test_expanded_is_the_greater_of_a_lesser_of_pair():
    """6(j)(1)(iv): max( min(200%+250k, 100%+scaled 7.5m), 125%+250k )."""
    out = 7_631_722
    a = 2.00 * out + ALLOWANCE
    b = out + 7_500_000 * S.salary_cap / BASE_CAP
    z = 1.25 * out + ALLOWANCE
    assert expanded(out, S, UNDER, BASE_CAP).amount == pytest.approx(max(min(a, b), z), abs=2)


def test_expanded_falls_back_to_125_percent_for_large_outgoing():
    """When 200% is the binding side, the scaled $7.5m cap makes (z) win."""
    out = 60_000_000
    got = expanded(out, S, UNDER, BASE_CAP)
    assert got.amount == pytest.approx(1.25 * out + ALLOWANCE, abs=2)


def test_allowance_disappears_above_the_first_apron():
    """6(j)(3): the $250,000 cushion is reduced to $0. Easy to miss, decisive in tight trades."""
    assert allowance_cushion(S.first_apron - 1, S) == ALLOWANCE
    assert allowance_cushion(S.first_apron + 1, S) == 0
    tight = standard(10_000_000, S, S.first_apron + 1)
    assert tight.amount == 10_000_000
    assert tight.allowance_applied == 0
    assert "allowance removed" in (tight.note or "")


def test_milwaukee_levert_needed_the_expanded_exception():
    """
    Out $7,631,722 (Harris + Prince), in $14,809,200 -- 194% of outgoing.
    The standard band cannot carry it; the expanded one can. Expanded is row E,
    which is why Milwaukee holds a first-apron ceiling.
    """
    out, inc = 7_631_722, 14_809_200
    assert not standard(out, S, UNDER).permits(inc)
    assert expanded(out, S, UNDER, BASE_CAP).permits(inc)
    chosen = best_allowance(out, inc, S, UNDER, BASE_CAP, aggregating=True)
    assert chosen is not None
    assert chosen.kind is MatchingExceptionKind.EXPANDED


def test_best_allowance_prefers_an_exception_with_no_apron_consequence():
    """A team should not be told it triggered a ceiling it did not need."""
    out, inc = 10_000_000, 10_100_000
    chosen = best_allowance(out, inc, S, UNDER, BASE_CAP, aggregating=False)
    assert chosen is not None
    assert chosen.kind is MatchingExceptionKind.STANDARD


def test_room_is_used_before_any_traded_player_exception():
    chosen = best_allowance(
        5_000_000, 12_000_000, S, UNDER, BASE_CAP, aggregating=False, cap_room=20_000_000
    )
    assert chosen is not None
    assert chosen.kind is MatchingExceptionKind.ROOM


def test_no_exception_permits_an_impossible_trade():
    assert best_allowance(1_000_000, 90_000_000, S, UNDER, BASE_CAP, aggregating=False) is None


def test_every_allowance_carries_its_citation():
    for got in (
        standard(1_000_000, S, UNDER),
        aggregated(1_000_000, S, UNDER),
        expanded(1_000_000, S, UNDER, BASE_CAP),
        room(1_000_000, S, UNDER),
    ):
        assert got.citation.article == "VII"
        assert got.citation.section.startswith("6(j)")


# -- structuring across several exceptions ---------------------------------


def test_splitting_outgoing_players_permits_more_than_one_exception():
    """
    Art. VII 6(j)(1)(i) lets one exception replace "one (1) Traded Player", and
    6(m) carves Section 6(j) out of its bar on combining exceptions. So a team
    sending four players may use four exceptions, earning the $250,000 allowance
    four times rather than once.
    """
    from engine.salary_matching import best_structure

    players = [20_000_000, 12_000_000, 9_435_741, 6_000_000]
    structured = best_structure(players, S, UNDER, BASE_CAP)
    single = expanded(sum(players), S, UNDER, BASE_CAP).amount
    assert structured.total_allowance > single
    assert structured.exception_count > 1


def test_a_single_outgoing_player_cannot_be_split():
    from engine.salary_matching import best_structure

    got = best_structure([47_435_741], S, UNDER, BASE_CAP)
    assert got.exception_count == 1
    assert got.total_allowance == expanded(47_435_741, S, UNDER, BASE_CAP).amount


def test_structuring_never_permits_less_than_a_single_exception():
    """Splitting is optional, so it can only help."""
    from engine.salary_matching import best_structure

    for players in ([5_000_000, 3_000_000], [30_000_000, 1_000_000], [9_000_000] * 3):
        structured = best_structure(players, S, UNDER, BASE_CAP)
        assert structured.total_allowance >= expanded(sum(players), S, UNDER, BASE_CAP).amount


def test_no_outgoing_players_permits_nothing():
    from engine.salary_matching import best_structure

    assert best_structure([], S, UNDER, BASE_CAP).total_allowance == 0
    assert best_structure([0, 0], S, UNDER, BASE_CAP).total_allowance == 0


def test_many_players_fall_back_without_enumerating_partitions():
    """Bell(12) is over four million; the fallback keeps this bounded."""
    from engine.salary_matching import MAX_PARTITIONED_PLAYERS, best_structure

    players = [3_000_000] * (MAX_PARTITIONED_PLAYERS + 4)
    got = best_structure(players, S, UNDER, BASE_CAP)
    assert got.total_allowance > 0
    assert got.exception_count in (1, len(players))
