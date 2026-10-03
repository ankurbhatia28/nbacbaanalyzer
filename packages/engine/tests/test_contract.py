"""Contract modelling, including the Over-38 test that corrected an earlier assumption."""

from datetime import date

from engine import (
    Contract,
    ContractType,
    ContractYear,
    Guarantee,
    GuaranteeType,
    Maybe,
)


def years(*specs):
    return tuple(ContractYear(season_id=s, cap_figure=v) for s, v in specs)


HARDEN = Contract(
    player_id="hardeja01",
    team_id="CLE",
    contract_type=ContractType.VETERAN,
    years=years(("2026-2027", 30_647_619), ("2027-2028", 32_180_000), ("2028-2029", 33_712_381)),
    signed_date=date(2026, 9, 8),
    trade_kicker_pct=Maybe.known(0.15),
)


def test_over_38_needs_four_seasons_not_just_age():
    """
    Art. VII 3(a)(2) requires a contract "covering four (4) or more Seasons"
    AND a season after the player turns 38. Harden (born 1989) reaches 38 during
    this three-year deal, but three is not four, so the rule does not apply.
    """
    assert HARDEN.covers_season_after_38th_birthday(1989) is True
    assert HARDEN.season_count == 3
    assert HARDEN.triggers_over_38_rule(1989) is False


def test_over_38_triggers_on_a_four_year_deal():
    four = Contract(
        player_id="test01",
        team_id="XXX",
        contract_type=ContractType.VETERAN,
        years=years(
            ("2026-2027", 10_000_000),
            ("2027-2028", 10_000_000),
            ("2028-2029", 10_000_000),
            ("2029-2030", 10_000_000),
        ),
    )
    assert four.triggers_over_38_rule(1989) is True


def test_four_year_deal_for_a_young_player_does_not_trigger():
    four = Contract(
        player_id="test02",
        team_id="XXX",
        contract_type=ContractType.VETERAN,
        years=years(
            ("2026-2027", 10_000_000),
            ("2027-2028", 10_000_000),
            ("2028-2029", 10_000_000),
            ("2029-2030", 10_000_000),
        ),
    )
    assert four.triggers_over_38_rule(2001) is False


def test_trade_kicker_defaults_to_unknown_not_absent():
    bare = Contract(
        player_id="x",
        team_id="Y",
        contract_type=ContractType.VETERAN,
        years=years(("2026-2027", 1_000_000)),
    )
    assert bare.trade_kicker_pct.is_unknown
    assert bare.no_trade_clause.is_unknown


def test_guarantee_kinds():
    full = ContractYear("2026-2027", 10_000_000)
    none = ContractYear("2026-2027", 10_000_000, guarantee=Guarantee(GuaranteeType.NONE))
    part = ContractYear(
        "2026-2027",
        10_000_000,
        guarantee=Guarantee(GuaranteeType.PARTIAL, 2_406_205, date(2027, 1, 10)),
    )
    assert full.guaranteed == 10_000_000
    assert none.guaranteed == 0
    assert part.guaranteed == 2_406_205


def test_an_unknown_guarantee_cannot_be_read_as_an_amount():
    """ADR-003: no source carries guarantee structure, and 'unknown' is not 'full'."""
    import pytest

    from engine.contract import Guarantee, GuaranteeType
    from engine.maybe import UnknownValueError

    with pytest.raises(UnknownValueError):
        Guarantee(GuaranteeType.UNKNOWN).guaranteed_amount(10_000_000)
