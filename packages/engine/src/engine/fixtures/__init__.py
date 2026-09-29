"""
Composable test fixtures.

Three libraries rather than one "fixture team", because the real league has
sixteen contract types, five apron classifications and five structurally
different pick-protection shapes -- a fifteen-man roster cannot carry that, and
a monolithic fixture localises failures poorly. A Phase 3 test composes what it
needs: second-apron shell + poison-pill contract + aggregation attempt.

Two principles, both learned the hard way:

  * **Boundaries, not typical values.** Salary matching is a threshold system,
    so fixtures sit exactly at, one dollar below, and one dollar above each
    edge -- expressed *relative to* Season constants, never as literals, or
    they silently stop testing boundaries when the cap moves.

  * **Negative fixtures are half the value.** Configurations that are illegal
    in a known way are what let Phase 3 assert the right violation code.
    Rejecting a trade for the wrong reason is still a failure.

Shells mirror real 2026-27 situations so their verdicts are checkable by
someone who follows the league. Over-38 and early-termination options are
invented, because no current contract exhibits either.
"""

from .contracts import (
    ALL_CONTRACT_FIXTURES,
    base_year_compensation,
    early_termination_option,
    fully_guaranteed,
    minimum_deal,
    non_guaranteed_year,
    over_38_contract,
    partially_guaranteed,
    player_option_year,
    poison_pill,
    re_signed_with_raise,
    recently_signed,
    team_option_year,
    ten_day,
    trade_kicker_known,
    trade_kicker_unknown,
    two_way,
)
from .picks import (
    ALL_PICK_FIXTURES,
    forfeited_firsts,
    own_outright,
    range_protected,
    rollover_then_seconds,
    stepien_violating,
    swap_right,
)
from .season import SEASON_2026_27, just_above, just_below
from .shells import (
    ALL_SHELLS,
    capped_below_ceiling,
    first_apron_capped,
    holds_divergence,
    pick_poverty,
    room_team,
    second_apron_uncapped,
)

__all__ = [
    "ALL_CONTRACT_FIXTURES",
    "ALL_PICK_FIXTURES",
    "ALL_SHELLS",
    "SEASON_2026_27",
    "base_year_compensation",
    "capped_below_ceiling",
    "early_termination_option",
    "first_apron_capped",
    "forfeited_firsts",
    "fully_guaranteed",
    "holds_divergence",
    "just_above",
    "just_below",
    "minimum_deal",
    "non_guaranteed_year",
    "over_38_contract",
    "own_outright",
    "partially_guaranteed",
    "pick_poverty",
    "player_option_year",
    "poison_pill",
    "range_protected",
    "re_signed_with_raise",
    "recently_signed",
    "rollover_then_seconds",
    "room_team",
    "second_apron_uncapped",
    "stepien_violating",
    "swap_right",
    "team_option_year",
    "ten_day",
    "trade_kicker_known",
    "trade_kicker_unknown",
    "two_way",
]
