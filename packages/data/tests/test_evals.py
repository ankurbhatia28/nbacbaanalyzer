"""
The eval harness itself.

Worth testing carefully: its first run reported eleven engine failures that were
all the harness over-claiming. A harness that cries wolf is worse than none,
because the natural response is to loosen the engine.
"""

from pathlib import Path

import pytest

from engine.fixtures import SEASON_2026_27
from nbadata.evals.corpus import TradeCase, load
from nbadata.evals.run import Outcome, evaluate, run
from nbadata.evals.seasons import load_seasons

BASE_CAP = 136_021_000
HEADER = "trade_id,date,trade_label,team,cash_received,tpes_generated,detail\n"


def write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "legs.csv"
    path.write_text(HEADER + body, encoding="utf-8")
    return path


def leg(trade_id, date, team, cap_sum, change):
    sign = "+" if change >= 0 else "-"
    detail = f"{team} Acquire: Cap Hit Sum: ${cap_sum:,} Cap Hit Change: {sign}${abs(change):,}"
    return f'{trade_id},{date},,{team},,,"{detail}"\n'


# -- corpus ---------------------------------------------------------------


def test_outgoing_is_derived_from_the_two_published_figures(tmp_path):
    path = write(tmp_path, leg(1, "2026-07-01", "MIL", 10_000_000, 4_000_000))
    case = load(path)[0]
    assert case.legs[0].incoming == 10_000_000
    assert case.legs[0].outgoing == 6_000_000  # sum minus change


def test_a_trade_that_does_not_balance_is_flagged(tmp_path):
    body = leg(1, "2026-07-01", "MIL", 10_000_000, 10_000_000) + leg(
        1, "2026-07-01", "BOS", 3_000_000, 3_000_000
    )
    case = load(path := write(tmp_path, body))[0]
    assert not case.balanced
    assert path.exists()


def test_a_balanced_trade_is_not_flagged(tmp_path):
    body = leg(1, "2026-07-01", "MIL", 10_000_000, 4_000_000) + leg(
        1, "2026-07-01", "BOS", 6_000_000, -4_000_000
    )
    assert load(write(tmp_path, body))[0].balanced


@pytest.mark.parametrize(
    "date,season",
    [("2026-07-01", "2026-2027"), ("2026-06-30", "2025-2026"), ("2023-07-01", "2023-2024")],
)
def test_the_salary_cap_year_runs_july_to_june(tmp_path, date, season):
    case = load(write(tmp_path, leg(1, date, "MIL", 0, 0)))[0]
    assert case.season_id == season


def test_trades_under_the_previous_cba_are_excluded(tmp_path):
    """D7: the engine models the 2023 agreement, so earlier trades test the wrong rules."""
    body = leg(1, "2022-02-10", "MIL", 0, 0) + leg(2, "2024-02-08", "BOS", 0, 0)
    cases = load(write(tmp_path, body))
    assert [c.trade_id for c in cases] == [2]


def test_a_missing_file_yields_no_cases():
    assert load(Path("/nonexistent/legs.csv")) == []


# -- runner ---------------------------------------------------------------


def case_with(*legs_):
    case = TradeCase(trade_id=1, date="2026-07-01")
    case.legs = list(legs_)
    return case


def test_sending_more_than_you_take_back_needs_no_exception():
    from nbadata.evals.corpus import Leg

    result = evaluate(
        case_with(Leg("MIL", 5_000_000, 9_000_000, 0, 0, False, 1)),
        SEASON_2026_27,
        BASE_CAP,
    )
    matching = [c for c in result.checks if c.check == "salary_matching"]
    assert matching[0].outcome is Outcome.PASS
    assert "no exception is needed" in matching[0].detail


def test_a_trade_within_an_exception_passes():
    from nbadata.evals.corpus import Leg

    result = evaluate(
        case_with(Leg("MIL", 10_100_000, 10_000_000, 0, 0, False, 1)),
        SEASON_2026_27,
        BASE_CAP,
    )
    matching = [c for c in result.checks if c.check == "salary_matching"]
    assert matching[0].outcome is Outcome.PASS


def test_taking_back_salary_while_sending_none_is_skipped_not_failed():
    """
    The bug the first run exposed. A team sending nothing and taking back $30m
    has used cap room or a standing exception, not broken a rule. Calling that a
    failure invites loosening the engine to silence it.
    """
    from nbadata.evals.corpus import Leg

    result = evaluate(
        case_with(Leg("MIL", 30_000_000, 0, 0, 0, False, 1)), SEASON_2026_27, BASE_CAP
    )
    matching = [c for c in result.checks if c.check == "salary_matching"]
    assert matching[0].outcome is Outcome.SKIPPED
    assert "cap room" in matching[0].detail
    assert not result.failed


def test_checks_needing_team_state_are_skipped_with_a_reason():
    from nbadata.evals.corpus import Leg

    result = evaluate(
        case_with(Leg("MIL", 20_000_000, 10_000_000, 0, 0, False, 1)),
        SEASON_2026_27,
        BASE_CAP,
    )
    skipped = {c.check for c in result.checks if c.outcome is Outcome.SKIPPED}
    assert {"hard_cap_ceiling", "allowance_removal"} <= skipped
    for check in result.checks:
        if check.outcome is Outcome.SKIPPED:
            assert check.detail, "a skipped check must say why"


def test_an_unbalanced_case_stops_before_evaluating_salaries():
    """Figures that do not add up should not be used to judge the engine."""
    from nbadata.evals.corpus import Leg

    case = case_with(Leg("MIL", 10_000_000, 0, 0, 0, False, 1))
    case.balanced = False
    result = evaluate(case, SEASON_2026_27, BASE_CAP)
    assert result.failed
    assert [c.check for c in result.checks] == ["corpus_balance"]


def test_a_season_with_no_cap_figures_is_skipped_not_guessed():
    report = run([case_with()], {}, BASE_CAP)
    assert report.cases[0].checks[0].check == "season_constants"
    assert report.cases[0].checks[0].outcome is Outcome.SKIPPED


def test_the_report_tallies_every_outcome():
    from nbadata.evals.corpus import Leg

    report = run(
        [case_with(Leg("MIL", 30_000_000, 0, 0, 0, False, 1))],
        {"2026-2027": SEASON_2026_27},
        BASE_CAP,
    )
    tally = report.tally()
    assert tally["salary_matching"]["skipped"] == 1
    assert "skipped" in report.render()


# -- seasons ---------------------------------------------------------------


def test_season_constants_load_from_the_scraped_history():
    seasons, base = load_seasons()
    if not seasons:
        pytest.skip("scraper output not present")
    assert "2023-2024" in seasons
    assert base == seasons["2023-2024"].salary_cap
