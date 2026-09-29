"""
Contract fixtures -- one per edge case.

Grounded in what the six scraped sources actually contain, so the inventory
reflects the league rather than my imagination. Two exceptions are noted where
they arise: early-termination options and Over-38 contracts appear nowhere in
the current data, so they are constructed.
"""

from __future__ import annotations

from datetime import date

from engine.contract import (
    Contract,
    ContractOption,
    ContractType,
    ContractYear,
    Guarantee,
    GuaranteeType,
    OptionType,
)
from engine.maybe import Maybe
from engine.provenance import Provenance, Source
from engine.restrictions import RestrictionReason, TradeRestriction
from engine.season import Season

FIXTURE = Provenance(Source.FIXTURE)


def _years(season: Season, *amounts: int) -> tuple[ContractYear, ...]:
    """Consecutive seasons starting at `season`, so fixtures follow the cap."""
    start = season.start_year
    return tuple(
        ContractYear(season_id=f"{start + i}-{start + i + 1}", cap_figure=amt)
        for i, amt in enumerate(amounts)
    )


def fully_guaranteed(season: Season, amount: int = 30_000_000) -> Contract:
    return Contract(
        player_id="fx_full",
        team_id="FIX",
        contract_type=ContractType.VETERAN,
        years=_years(season, amount, amount, amount),
        signed_date=date(season.start_year, 7, 6),
        trade_kicker_pct=Maybe.absent(),
        no_trade_clause=Maybe.absent(),
        provenance=FIXTURE,
    )


def partially_guaranteed(season: Season) -> Contract:
    """A partial guarantee with the date it converts -- drives Phase 7 branching."""
    y = _years(season, 10_000_000)[0]
    return Contract(
        player_id="fx_partial",
        team_id="FIX",
        contract_type=ContractType.VETERAN,
        years=(
            ContractYear(
                y.season_id,
                y.cap_figure,
                guarantee=Guarantee(
                    GuaranteeType.PARTIAL, 2_406_205, date(season.start_year + 1, 1, 10)
                ),
            ),
        ),
        trade_kicker_pct=Maybe.absent(),
        provenance=FIXTURE,
    )


def non_guaranteed_year(season: Season) -> Contract:
    y = _years(season, 2_464_849)[0]
    return Contract(
        player_id="fx_nonguar",
        team_id="FIX",
        contract_type=ContractType.VETERAN,
        years=(ContractYear(y.season_id, y.cap_figure, guarantee=Guarantee(GuaranteeType.NONE)),),
        trade_kicker_pct=Maybe.absent(),
        provenance=FIXTURE,
    )


def team_option_year(season: Season) -> Contract:
    a, b = _years(season, 13_826_040, 17_434_637)
    return Contract(
        player_id="fx_teamopt",
        team_id="FIX",
        contract_type=ContractType.ROOKIE_FIRST_ROUND,
        years=(
            a,
            ContractYear(
                b.season_id,
                b.cap_figure,
                option=ContractOption(
                    OptionType.TEAM, date(season.start_year, 10, 31), b.cap_figure
                ),
            ),
        ),
        trade_kicker_pct=Maybe.absent(),
        provenance=FIXTURE,
    )


def player_option_year(season: Season) -> Contract:
    """Mirrors Harden's 2028-29 player option plus his trade kicker."""
    a, b, c = _years(season, 30_647_619, 32_180_000, 33_712_381)
    return Contract(
        player_id="fx_playeropt",
        team_id="FIX",
        contract_type=ContractType.VETERAN,
        years=(
            a,
            b,
            ContractYear(
                c.season_id,
                c.cap_figure,
                option=ContractOption(
                    OptionType.PLAYER, date(season.start_year + 2, 6, 29), c.cap_figure
                ),
            ),
        ),
        signed_date=date(season.start_year, 9, 8),
        trade_kicker_pct=Maybe.known(0.15),
        provenance=FIXTURE,
    )


def early_termination_option(season: Season) -> Contract:
    """INVENTED. No current contract carries an ETO, but the CBA provides for one."""
    a, b, c = _years(season, 20_000_000, 21_000_000, 22_000_000)
    return Contract(
        player_id="fx_eto",
        team_id="FIX",
        contract_type=ContractType.VETERAN,
        years=(
            a,
            b,
            ContractYear(
                c.season_id,
                c.cap_figure,
                option=ContractOption(
                    OptionType.EARLY_TERMINATION, date(season.start_year + 2, 6, 29)
                ),
            ),
        ),
        trade_kicker_pct=Maybe.absent(),
        provenance=FIXTURE,
    )


def over_38_contract(season: Season) -> Contract:
    """
    INVENTED. Four seasons extending past the player's 38th birthday, which is
    what Art. VII 3(a)(2) requires -- age alone is not enough. Zero of the 92
    four-plus-year contracts in the real data trigger this, which is the rule
    working as designed.
    """
    return Contract(
        player_id="fx_over38",
        team_id="FIX",
        contract_type=ContractType.VETERAN,
        years=_years(season, 25_000_000, 25_000_000, 25_000_000, 25_000_000),
        signed_date=date(season.start_year, 7, 6),
        trade_kicker_pct=Maybe.absent(),
        provenance=FIXTURE,
    )


OVER_38_BIRTH_YEAR = 1989
"""Pairs with over_38_contract(): reaches 38 inside the four-season term."""


def poison_pill(season: Season) -> Contract:
    """
    A rookie-scale extension not yet in effect. Outgoing and incoming salary are
    valued differently for the two teams -- counterintuitive, and a good demo.
    """
    return Contract(
        player_id="fx_poison",
        team_id="FIX",
        contract_type=ContractType.ROOKIE_EXTENSION,
        years=_years(season, 5_000_000, 30_000_000, 32_000_000),
        signed_date=date(season.start_year - 1, 10, 21),
        trade_kicker_pct=Maybe.absent(),
        provenance=FIXTURE,
    )


def base_year_compensation(season: Season) -> Contract:
    """Re-signed with a large raise; outgoing value differs from cap figure."""
    return Contract(
        player_id="fx_byc",
        team_id="FIX",
        contract_type=ContractType.VETERAN,
        years=_years(season, 24_000_000, 25_000_000),
        signed_date=date(season.start_year, 7, 10),
        trade_kicker_pct=Maybe.absent(),
        provenance=FIXTURE,
    )


def trade_kicker_known(season: Season, pct: float = 0.15) -> Contract:
    return Contract(
        player_id="fx_kicker",
        team_id="FIX",
        contract_type=ContractType.VETERAN,
        years=_years(season, 21_000_000),
        trade_kicker_pct=Maybe.known(pct),
        no_trade_clause=Maybe.absent(),
        provenance=FIXTURE,
    )


def trade_kicker_unknown(season: Season) -> Contract:
    """
    The ADR-003 case, and the common one: no source we found publishes kickers
    reliably. Any verdict touching this contract must carry an assumption.
    """
    return Contract(
        player_id="fx_kicker_unk",
        team_id="FIX",
        contract_type=ContractType.VETERAN,
        years=_years(season, 21_000_000),
        trade_kicker_pct=Maybe.unknown(),
        no_trade_clause=Maybe.unknown(),
        provenance=FIXTURE,
    )


def minimum_deal(season: Season, years_of_service: int = 5) -> Contract:
    return Contract(
        player_id="fx_min",
        team_id="FIX",
        contract_type=ContractType.MINIMUM,
        years=_years(season, season.minimum_for(years_of_service)),
        trade_kicker_pct=Maybe.absent(),
        provenance=FIXTURE,
    )


def two_way(season: Season) -> Contract:
    return Contract(
        player_id="fx_2w",
        team_id="FIX",
        contract_type=ContractType.TWO_WAY,
        years=_years(season, 0),
        trade_kicker_pct=Maybe.absent(),
        provenance=FIXTURE,
    )


def ten_day(season: Season) -> Contract:
    return Contract(
        player_id="fx_10d",
        team_id="FIX",
        contract_type=ContractType.TEN_DAY,
        years=_years(season, 120_000),
        trade_kicker_pct=Maybe.absent(),
        provenance=FIXTURE,
    )


def recently_signed(season: Season) -> tuple[Contract, TradeRestriction]:
    """Signed too recently to be traded -- the Dec 15 / three-month rule."""
    c = Contract(
        player_id="fx_recent",
        team_id="FIX",
        contract_type=ContractType.FREE_AGENT_SIGNING,
        years=_years(season, 14_100_000),
        signed_date=date(season.start_year, 7, 10),
        trade_kicker_pct=Maybe.absent(),
        provenance=FIXTURE,
    )
    r = TradeRestriction(
        player_id="fx_recent",
        reason=RestrictionReason.RECENTLY_SIGNED,
        expires=date(season.start_year, 12, 15),
        blocks_trade_entirely=True,
    )
    return c, r


def re_signed_with_raise(season: Season) -> tuple[Contract, TradeRestriction]:
    """Aggregation-blocked for two months, but tradeable on its own."""
    c = Contract(
        player_id="fx_raise",
        team_id="FIX",
        contract_type=ContractType.VETERAN,
        years=_years(season, 28_000_000),
        signed_date=date(season.start_year, 7, 6),
        trade_kicker_pct=Maybe.absent(),
        provenance=FIXTURE,
    )
    r = TradeRestriction(
        player_id="fx_raise",
        reason=RestrictionReason.RE_SIGNED_WITH_RAISE,
        expires=date(season.start_year, 9, 6),
        blocks_trade_entirely=False,
        blocks_aggregation_only=True,
    )
    return c, r


ALL_CONTRACT_FIXTURES = (
    fully_guaranteed,
    partially_guaranteed,
    non_guaranteed_year,
    team_option_year,
    player_option_year,
    early_termination_option,
    over_38_contract,
    poison_pill,
    base_year_compensation,
    trade_kicker_known,
    trade_kicker_unknown,
    minimum_deal,
    two_way,
    ten_day,
)
"""Single-return fixtures, for tests that want to sweep every shape."""
