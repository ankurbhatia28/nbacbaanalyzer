"""
A proposed trade, checked by the engine against the league database (7.4).

The trade builder sends moves -- "this player, from this team, to that one" --
and gets back the engine's verdict on the deal as a whole and on each team's
side of it. Nothing here decides legality: `engine.validate_trade` does, over
`TeamState`s from `state.team_state`, the same bridge the cap sheet reads. This
module only turns moves into the engine's `Trade`, and the verdict into
something a page can show.

**What the verdict does not cover is said, every time** (ADR-003). The engine
checks what it was built to check (`CHECKS_IMPLEMENTED`); several of those
checks run on data no source carries, and the response names them rather than
letting "legal" read as "nothing else could be wrong":

  trade kickers        unknown on every contract -> assumed absent, as an
                       assumption on the verdict (the engine records it)
  no-trade clauses     unknown on every contract -> listed per player sent
  trade restrictions   no source carries recently-signed or recently-acquired
                       restrictions, so that check runs on nothing
  aggregation bar      needs the date a player was acquired; Basketball-
                       Reference's signing date is used where it exists
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field, replace
from datetime import date
from typing import Any

from engine.trade import Trade, TradeLeg
from engine.validate import validate_trade
from engine.violations import Verdict

from .state import CURRENT_SEASON, player_names, team, team_state

MAX_MOVES = 16
"""More players than any real trade moves. A request for more is not a trade."""

UNSOURCED_CHECKS = (
    "No source carries trade restrictions on recently signed or acquired players, "
    "so none are applied.",
    "No source carries no-trade clauses or trade kickers; kickers are assumed absent.",
)


class TradeError(ValueError):
    """A trade that cannot be checked as given. The message is for the reader."""


@dataclass(frozen=True, slots=True)
class Move:
    player: str
    from_team: str
    to_team: str


@dataclass
class Side:
    """One team's half of the deal, before and after."""

    team: str
    name: str
    sends: list[dict[str, Any]] = field(default_factory=list)
    receives: list[dict[str, Any]] = field(default_factory=list)
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    violations: list[dict[str, Any]] = field(default_factory=list)


def _position(state: Any) -> dict[str, Any]:
    ceiling = state.effective_ceiling()
    return {
        "cap": state.cap_salary(),
        "apron": state.apron_team_salary(),
        "status": state.apron_status().value,
        "standard_contracts": state.roster.standard_count if state.roster else None,
        "ceiling": {"level": ceiling[0], "amount": ceiling[1]} if ceiling else None,
    }


def check(
    conn: sqlite3.Connection, moves: list[Move], as_of: date
) -> tuple[Verdict, list[Side], Trade]:
    """
    The engine's verdict on `moves`. Raises `TradeError` for a trade that is
    not one -- a player the team does not hold, one team, a player moved twice
    -- and `state.MissingDataError` for a team that does not exist.
    """
    if not moves:
        raise TradeError("Add a player to the trade.")
    if len(moves) > MAX_MOVES:
        raise TradeError(f"A trade here moves at most {MAX_MOVES} players.")
    teams = sorted({m.from_team for m in moves} | {m.to_team for m in moves})
    if len(teams) < 2:
        raise TradeError("A trade needs at least two teams.")
    for m in moves:
        if m.from_team == m.to_team:
            raise TradeError(f"{m.player} is being sent from {m.from_team} to itself.")
    players = [m.player for m in moves]
    if len(set(players)) != len(players):
        raise TradeError("A player appears in the trade twice.")

    states = {t: team_state(conn, t, CURRENT_SEASON) for t in teams}
    names = player_names(conn, players)
    legs = {t: TradeLeg(team_id=t) for t in teams}
    for m in moves:
        held = states[m.from_team]
        contract = next(
            (
                c
                for c in held.contracts
                if c.player_id == m.player and c.cap_figure(CURRENT_SEASON) > 0
            ),
            None,
        )
        if contract is None:
            who = names.get(m.player, m.player)
            raise TradeError(f"{who} is not under contract with {m.from_team} this season.")
        legs[m.from_team].sends.append(contract)
        legs[m.to_team].receives.append(contract)

    trade = Trade(legs=list(legs.values()), as_of=as_of, season_id=CURRENT_SEASON)
    verdict = validate_trade(trade, states, base_season_cap(conn))

    sides = []
    for t in teams:
        leg = legs[t]
        state = states[t]
        sent = {c.player_id for c in leg.sends}
        after_state = replace(
            state,
            contracts=[c for c in state.contracts if c.player_id not in sent] + leg.receives,
            roster=replace(
                state.roster,
                standard_count=state.roster.standard_count - len(leg.sends) + len(leg.receives),
            )
            if state.roster
            else None,
        )
        line = _player_line(names)
        sides.append(
            Side(
                team=t,
                name=team(conn, t).name,
                sends=[line(c) for c in leg.sends],
                receives=[line(c) for c in leg.receives],
                before=_position(state),
                after=_position(after_state),
                violations=[
                    {
                        "code": v.code.value,
                        "detail": v.detail,
                        "subject": names.get(v.subject, v.subject) if v.subject else None,
                        "citation": v.citation.short,
                        "title": v.citation.title,
                    }
                    for v in verdict.violations
                    if v.team_id == t
                ],
            )
        )
    return verdict, sides, trade


def _player_line(names: dict[str, str]) -> Any:
    def line(contract: Any) -> dict[str, Any]:
        return {
            "player": contract.player_id,
            "name": names.get(contract.player_id, contract.player_id),
            "amount": contract.cap_figure(CURRENT_SEASON),
            "no_trade_clause": "unknown"
            if contract.no_trade_clause.is_unknown
            else bool(contract.no_trade_clause.value),
        }

    return line


def current_teams(conn: sqlite3.Connection, keys: list[str]) -> list[dict[str, Any]]:
    """
    Where each player is under contract this season, for seeding the builder
    from a chat answer. A player on no payroll is returned with no team rather
    than dropped, so the page can say so.
    """
    names = player_names(conn, keys)
    out = []
    for key in keys:
        row = conn.execute(
            "SELECT c.team_key FROM contracts c JOIN contract_years y USING (contract_id) "
            "WHERE c.player_key = ? AND y.season_id = ? AND y.cap_figure > 0",
            (key, CURRENT_SEASON),
        ).fetchone()
        out.append({"player": key, "name": names.get(key, key), "team": row[0] if row else None})
    return out


def base_season_cap(conn: sqlite3.Connection) -> int:
    """
    The 2023-24 Salary Cap, the Expanded exception's fixed denominator
    (Art. VII §6(j)(1)(iv)). Read from the database rather than restated.
    """
    row = conn.execute("SELECT salary_cap FROM seasons WHERE season_id = '2023-2024'").fetchone()
    if row is None or row[0] is None:
        raise TradeError("The database has no 2023-24 Salary Cap, which salary matching needs.")
    return int(row[0])


def to_json(verdict: Verdict, sides: list[Side], trade: Trade) -> dict[str, Any]:
    return {
        "legal": verdict.legal,
        "conditional": verdict.is_conditional,
        "season": trade.season_id,
        "as_of": trade.as_of.isoformat(),
        "sides": [
            {
                "team": s.team,
                "name": s.name,
                "sends": s.sends,
                "receives": s.receives,
                "outgoing": sum(p["amount"] for p in s.sends),
                "incoming": sum(p["amount"] for p in s.receives),
                "before": s.before,
                "after": s.after,
                "violations": s.violations,
            }
            for s in sides
        ],
        "assumptions": [
            {"subject": a.subject, "field": a.field_name, "assumed": a.assumed, "reason": a.reason}
            for a in verdict.assumptions
        ],
        "notes": list(verdict.notes),
        "unsourced": list(UNSOURCED_CHECKS),
    }
