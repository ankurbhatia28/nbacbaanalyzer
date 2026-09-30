"""
The frozen first-round pick, Art. VII Section 2(f).

The second-apron consequence that is not a Transaction Restrictions Table row,
so it does not fall out of 2(e)(2)(i)(A) with the others.
"""

import pytest

from engine.draft_pick_penalty import (
    FIRST_APPLICABLE_SALARY_CAP_YEAR,
    evaluate,
    frozen_draft_year,
    penalised_pick_order,
)


def test_the_cba_worked_example_reconciles():
    """
    From the document: a Second Apron Team for the 2024-25 Salary Cap Year
    "would be prohibited from trading its 2032 first round draft pick".
    """
    assert frozen_draft_year(2024) == 2032


@pytest.mark.parametrize("trigger,draft", [(2024, 2032), (2025, 2033), (2027, 2035)])
def test_the_freeze_horizon(trigger, draft):
    assert frozen_draft_year(trigger) == draft


def test_the_pick_is_frozen_and_unresolved_while_the_window_is_still_running():
    """
    A team in 2026 cannot know whether its 2032 pick will be penalised, because
    2027 and 2028 have not happened. Reporting a provisional answer as settled
    would be a guess.
    """
    got = evaluate(
        trigger_salary_cap_year=2024,
        second_apron_in={2024},
        known_through_salary_cap_year=2026,
    )
    assert got.frozen
    assert not got.penalised
    assert not got.resolved
    assert "not yet determined" in got.describe()


def test_the_penalty_can_be_settled_early_once_two_years_are_over_the_line():
    """Two of four is decisive whether or not the window has closed."""
    got = evaluate(
        trigger_salary_cap_year=2024,
        second_apron_in={2024, 2025, 2026},
        known_through_salary_cap_year=2026,
    )
    assert got.penalised
    assert got.resolved


def test_two_of_the_next_four_years_imposes_the_penalty():
    """The CBA's own Team A: 2024-25, plus 2025-26 and 2028-29."""
    got = evaluate(trigger_salary_cap_year=2024, second_apron_in={2024, 2025, 2028})
    assert got.penalised
    assert got.frozen  # a penalised pick is still untradeable
    assert got.second_apron_years == (2025, 2028)
    assert "final selection" in got.describe()


def test_one_later_year_releases_the_pick_after_the_third_compliant_season():
    got = evaluate(trigger_salary_cap_year=2024, second_apron_in={2024, 2026})
    assert not got.penalised
    assert not got.frozen
    # compliant years are 2025, 2027, 2028 -- the third is 2028
    assert got.released_after_salary_cap_year == 2028


def test_no_later_years_over_the_line_releases_it_at_the_third_year():
    got = evaluate(trigger_salary_cap_year=2024, second_apron_in={2024})
    assert got.released_after_salary_cap_year == 2027


def test_a_team_never_over_the_line_is_unaffected():
    got = evaluate(trigger_salary_cap_year=2024, second_apron_in=set())
    assert not got.frozen and not got.penalised
    assert "unaffected" in got.describe()


def test_the_penalty_does_not_apply_before_2024_25():
    """2(f)(2): "Beginning with the 2024-25 Salary Cap Year"."""
    assert FIRST_APPLICABLE_SALARY_CAP_YEAR == 2024
    got = evaluate(trigger_salary_cap_year=2023, second_apron_in={2023, 2024, 2025})
    assert not got.frozen and not got.penalised


def test_penalised_picks_select_in_inverse_order_of_winning_percentage():
    """
    2(f)(1)(ii): the better record selects last. The CBA's example has Team A
    with the better percentage making the final selection.
    """
    order = penalised_pick_order([("A", 0.610), ("B", 0.400), ("C", 0.520)])
    assert order == ["B", "C", "A"]


def test_every_status_carries_the_citation():
    got = evaluate(trigger_salary_cap_year=2024, second_apron_in={2024})
    assert got.citation.article == "VII"
    assert got.citation.section == "2(f)"
