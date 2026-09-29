"""
Rules from the NBA Constitution and By-Laws (2024), not the CBA.

A separate namespace on purpose. These are league governance rules agreed among
the Members, not collective bargaining provisions -- the CBA says so explicitly
at p. 322: "nothing contained in this Agreement shall be deemed to be an
agreement of the Players Association to any provision of the NBA Constitution
and By-Laws."

The distinction matters for a system whose claim is that its citations are
trustworthy. A verdict resting on By-Law 7.03 should say so rather than implying
the CBA prohibits the trade.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class ByLaw:
    section: str
    page: int
    title: str

    def __str__(self) -> str:
        return f"NBA Constitution and By-Laws {self.section} (p. {self.page})"

    @property
    def short(self) -> str:
        return f"By-Law {self.section}"


TRADING_DATES = ByLaw("4.01(a)", 69, "Trading Dates")
FIRST_ROUND_DRAFT_CHOICE = ByLaw("7.03", 85, "First Round Draft Choice")
ADDITIONAL_DRAFT_RULES = ByLaw("7.05", 85, "Additional Rules Concerning Draft")

ALL_BY_LAWS: tuple[ByLaw, ...] = (
    TRADING_DATES,
    FIRST_ROUND_DRAFT_CHOICE,
    ADDITIONAL_DRAFT_RULES,
)


# ----------------------------------------------------------------------
# 7.03 First Round Draft Choice -- the rule commonly called "Stepien"
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StepienResult:
    permitted: bool
    bare_years: tuple[int, ...] = ()
    consecutive_pair: tuple[int, int] | None = None
    by_law: ByLaw = FIRST_ROUND_DRAFT_CHOICE
    detail: str | None = None


def consecutive_bare_years(bare: set[int]) -> tuple[int, int] | None:
    """The first pair of consecutive years with no first-round pick, if any."""
    for year in sorted(bare):
        if year + 1 in bare:
            return (year, year + 1)
    return None


def check_first_round_rule(
    *,
    years_examined: range,
    holds_first_in: dict[int, bool],
    years_possibly_lost: set[int] | None = None,
) -> StepienResult:
    """
    By-Law 7.03: a Member may not trade a first-round pick "if the result of such
    trade or exchange **may be** to leave the Member without first-round picks in
    any two (2) consecutive future NBA Drafts."

    Two things follow from the wording and both matter:

    * "without first-round picks" -- *any* first satisfies it, including another
      team's. A team whose own pick is gone but who holds someone else's is not
      bare that year. Getting this wrong makes a legal position look illegal.
    * "may be" -- the test is what *could* happen, so a protected pick that might
      not convey counts as possibly absent. `years_possibly_lost` carries those.
    """
    possibly_lost = years_possibly_lost or set()
    bare = {
        year
        for year in years_examined
        if not holds_first_in.get(year, False) or year in possibly_lost
    }
    pair = consecutive_bare_years(bare)
    if pair is None:
        return StepienResult(
            True,
            tuple(sorted(bare)),
            None,
            detail="no two consecutive future Drafts would be left bare",
        )
    return StepienResult(
        False,
        tuple(sorted(bare)),
        pair,
        detail=f"would leave no first-round pick in {pair[0]} and {pair[1]}, which are consecutive",
    )


def may_sell_first_round_pick_for_cash() -> bool:
    """
    By-Law 7.03, first clause: "No Member may sell its rights to select a player
    in the first round of any NBA Draft for cash or its equivalent."

    A flat prohibition, distinct from the consecutive-years test. Note this is
    separate from the CBA's row I, which permits paying cash in a trade at the
    cost of a second-apron ceiling -- selling a *first-round pick* for cash is
    barred outright by league rule.
    """
    return False


# ----------------------------------------------------------------------
# 4.01 Trading Dates
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TradingWindow:
    open_: bool
    by_law: ByLaw = TRADING_DATES
    detail: str = ""


def deadline_for(all_star_game: date) -> date:
    """
    By-Law 4.01(a): 3 p.m. eastern on the **second Thursday prior** to that
    Season's All-Star Game. The date moves with the All-Star Game rather than
    being fixed, which is why it is computed rather than stored.
    """
    days_since_thursday = (all_star_game.weekday() - 3) % 7
    from datetime import timedelta

    most_recent_thursday = all_star_game - timedelta(days=days_since_thursday or 7)
    return most_recent_thursday - timedelta(days=7)


def trading_window(
    *,
    when: date,
    all_star_game: date,
    last_regular_season_game: date,
    in_moratorium: bool = False,
    player_on_postseason_roster_of_active_team: bool = False,
) -> TradingWindow:
    """
    By-Law 4.01(a). Closed from the deadline until the day after the last Regular
    Season Game, then open again with two carve-outs.
    """
    if in_moratorium:
        return TradingWindow(
            False, detail="no Assignment Transactions during the Moratorium Period"
        )
    deadline = deadline_for(all_star_game)
    if deadline < when <= last_regular_season_game:
        return TradingWindow(
            False,
            detail=f"closed from 3 p.m. ET on {deadline.isoformat()} until the day "
            f"after the last Regular Season Game",
        )
    if when > last_regular_season_game and player_on_postseason_roster_of_active_team:
        return TradingWindow(
            False,
            detail="a Member in the Postseason may not assign a Player on its Postseason "
            "Roster until eliminated",
        )
    return TradingWindow(True, detail="Assignment Transactions permitted")


PICK_HORIZON_NOT_SOURCED = (
    "The commonly cited limit on trading picks more than seven Drafts ahead is in "
    "neither the CBA nor the Constitution. By-Law 7.05 lets the Board of Governors "
    "adopt additional Draft rules, which is the likely home, and those are not "
    "published in either document. Not implemented."
)
"""Task 3.16: recorded rather than guessed at."""
