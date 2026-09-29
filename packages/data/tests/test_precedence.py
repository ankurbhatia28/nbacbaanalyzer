"""Precedence is a recorded decision, not an emergent property of code order."""

from nbadata.ingest.precedence import PRECEDENCE, Src, winner


def test_bbref_wins_salary_over_fanspo():
    # B-R publishes six seasons; Fanspo's payload is current-season only.
    assert winner("salary_by_season", {Src.FANSPO, Src.BBREF_CONTRACTS}) is Src.BBREF_CONTRACTS


def test_spotrac_is_the_only_source_of_guarantee_dates():
    assert winner("guarantee_date", {Src.SPOTRAC}) is Src.SPOTRAC
    assert winner("guarantee_date", {Src.BBREF_CONTRACTS, Src.FANSPO}) is None


def test_salaryswish_owns_ceilings_and_cash():
    assert winner("hard_cap_ceiling", {Src.SALARYSWISH, Src.SPOTRAC}) is Src.SALARYSWISH
    assert winner("cash_in_trade", {Src.SALARYSWISH}) is Src.SALARYSWISH


def test_fanspo_season_constants_beat_the_user_projections():
    # Fanspo carries actuals back to 2011-12; the user CSVs are projections,
    # which Phase 4 must not validate history against.
    assert winner("season_constants", {Src.USER_CSV, Src.FANSPO}) is Src.FANSPO


def test_unknown_field_has_no_winner():
    assert winner("not_a_field", {Src.FANSPO}) is None


def test_every_ranking_is_non_empty_and_duplicate_free():
    for field_name, sources in PRECEDENCE.items():
        assert sources, field_name
        assert len(set(sources)) == len(sources), field_name
