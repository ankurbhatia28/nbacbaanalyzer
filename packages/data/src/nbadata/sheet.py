"""
A team's cap sheet (7.5): every line on its books, the totals the engine
computes from them, and the four thresholds those totals are measured against.

Built from `state.team_state`, so the sheet and any engine verdict read the
same `TeamState` and cannot disagree about a team's salary. The sheet adds
nothing the engine does not compute -- it lays the engine's three totals
beside the lines they sum, and says for each line which totals it counts in.
That is the point of showing it: a cap hold counts toward room but not the
aprons (Art. VII §2(e)(1)(iv)), and a reader who cannot see that will
"correct" a figure that is right.

**Unknowns are shown as unknown** (ADR-003). Guarantees, trade kickers and
no-trade clauses are unknown on every contract the sources carry, and the
sheet says so once, as a warning, rather than leaving the cells blank as
though blank meant "none".

Trade exceptions are read directly from the database, as `state` says: the
engine cannot hold them without a creation date. Their source is Spotrac via
the Wayback Machine, months older than the payroll, so each is checked
against the payroll's date and marked expired rather than trusted.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from engine.holds import HoldKind
from engine.team_state import TeamState

from .query.provenance import source_dates
from .state import CURRENT_SEASON, _date, player_names, team, team_state

LATER_SEASONS = 4
"""Columns after the current season. B-R's grid runs further; the rest is noise."""

SHEET_SOURCES = ("fanspo", "bbref_contracts", "salaryswish")
"""Payroll and thresholds, later seasons, hard-cap ceilings. Trade exceptions date themselves."""


@dataclass(frozen=True, slots=True)
class Line:
    """One row of the sheet. `cap` and `apron` are what it counts in each total."""

    kind: str  # contract | hold | dead
    player: str | None
    name: str | None
    amount: int
    cap: int
    apron: int
    label: str | None = None
    later: dict[str, int] = field(default_factory=dict)
    options: dict[str, str] = field(default_factory=dict)
    source: str = "fanspo"

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "player": self.player,
            "name": self.name,
            "amount": self.amount,
            "counts": {"cap": self.cap, "apron": self.apron},
            "label": self.label,
            "later": dict(self.later),
            "options": dict(self.options),
            "source": self.source,
        }


@dataclass(frozen=True, slots=True)
class HeldException:
    amount: int
    available: int | None
    expires: str | None
    expired: bool | None
    reason: str | None
    source: str
    as_of: str | None

    def to_json(self) -> dict[str, Any]:
        return {
            "amount": self.amount,
            "available": self.available,
            "expires": self.expires,
            "expired": self.expired,
            "reason": self.reason,
            "source": self.source,
            "as_of": self.as_of,
        }


@dataclass(frozen=True, slots=True)
class CapSheet:
    team: str
    name: str
    season: str
    thresholds: dict[str, int]
    totals: dict[str, int]
    status: str
    ceiling: dict[str, Any] | None
    lines: list[Line]
    later_seasons: list[str]
    later_totals: dict[str, int]
    trade_exceptions: list[HeldException]
    sources: dict[str, str]
    warnings: list[str]

    def to_json(self) -> dict[str, Any]:
        return {
            "team": self.team,
            "name": self.name,
            "season": self.season,
            "thresholds": dict(self.thresholds),
            "totals": dict(self.totals),
            "status": self.status,
            "ceiling": self.ceiling,
            "lines": [line.to_json() for line in self.lines],
            "later_seasons": list(self.later_seasons),
            "later_totals": dict(self.later_totals),
            "trade_exceptions": [t.to_json() for t in self.trade_exceptions],
            "sources": dict(self.sources),
            "warnings": list(self.warnings),
        }


def _lines(state: TeamState, names: dict[str, str], later: list[str]) -> list[Line]:
    season_id = state.season.season_id
    out: list[Line] = []
    for c in state.contracts:
        amount = c.cap_figure(season_id)
        out.append(
            Line(
                kind="contract",
                player=c.player_id,
                name=names.get(c.player_id),
                amount=amount,
                cap=amount,
                apron=amount,
                later={s: c.cap_figure(s) for s in later if c.cap_figure(s)},
                options={
                    y.season_id: y.option.kind.value
                    for y in c.years
                    if y.option is not None and y.season_id in (season_id, *later)
                },
                # D18: the current season is Fanspo's payroll, later ones B-R's.
                source="fanspo",
            )
        )
    for h in state.cap_holds:
        apron = 0
        if h.kind is HoldKind.QUALIFYING_OFFER:
            apron = h.qualifying_offer or h.amount
        out.append(
            Line(
                kind="hold",
                player=h.player_id,
                name=names.get(h.player_id) if h.player_id else None,
                amount=h.amount,
                cap=h.amount,
                apron=apron,
                label=h.description,
            )
        )
    for d in state.dead_money:
        out.append(
            Line(
                kind="dead",
                player=d.player_id,
                name=names.get(d.player_id) if d.player_id else None,
                amount=d.amount,
                cap=d.amount,
                apron=d.amount,
            )
        )
    order = {"contract": 0, "dead": 1, "hold": 2}
    return sorted(out, key=lambda line: (order[line.kind], -line.amount))


def _trade_exceptions(
    conn: sqlite3.Connection, team_key: str, on: date | None
) -> list[HeldException]:
    out = []
    for amount, available, expires, reason, source, as_of in conn.execute(
        "SELECT amount, available, expires, reason, source, as_of FROM trade_exceptions "
        "WHERE team_key = ? ORDER BY amount DESC",
        (team_key,),
    ):
        when = _date(expires)
        out.append(
            HeldException(
                amount=int(amount),
                available=int(available) if available is not None else None,
                expires=when.isoformat() if when else expires,
                expired=(when < on) if when and on else None,
                reason=reason or None,
                source=str(source),
                as_of=as_of,
            )
        )
    return out


def cap_sheet(conn: sqlite3.Connection, team_key: str) -> CapSheet:
    """The current season's sheet. Raises `MissingDataError` for an unknown team."""
    t = team(conn, team_key)
    state = team_state(conn, team_key, CURRENT_SEASON)
    s = state.season

    later = sorted({y.season_id for c in state.contracts for y in c.years} - {CURRENT_SEASON})
    later = [x for x in later if x > CURRENT_SEASON][:LATER_SEASONS]
    keys = [c.player_id for c in state.contracts]
    keys += [h.player_id for h in state.cap_holds if h.player_id]
    keys += [d.player_id for d in state.dead_money if d.player_id]
    lines = _lines(state, player_names(conn, keys), later)

    dates = source_dates(conn)
    payroll_date = _date(dates.get("fanspo"))
    exceptions = _trade_exceptions(conn, team_key, payroll_date)

    ceiling = None
    binding = state.effective_ceiling()
    if binding is not None:
        ceiling = {
            "level": binding[0],
            "amount": binding[1],
            "room": state.room_below_ceiling(),
            "triggers": sorted(
                {c.source_transaction for c in state.ceilings.ceilings if c.source_transaction}
            ),
        }

    warnings = [
        "Guarantees, trade kickers and no-trade clauses are unknown for every contract: "
        "no source this project reads carries them.",
    ]
    if any(line.kind == "hold" and line.player is None for line in lines):
        warnings.append("Some cap holds are listed by the source without a player.")
    if exceptions:
        warnings.append(
            "Trade exceptions come from an archived Spotrac page, older than the payroll; "
            "expiry is checked against the payroll's date."
        )

    return CapSheet(
        team=t.key,
        name=t.name,
        season=CURRENT_SEASON,
        thresholds={
            "salary_cap": s.salary_cap,
            "tax_level": s.tax_level,
            "first_apron": s.first_apron,
            "second_apron": s.second_apron,
        },
        totals={
            "committed": state.committed_salary(),
            "cap": state.cap_salary(),
            "apron": state.apron_team_salary(),
        },
        status=state.apron_status().value,
        ceiling=ceiling,
        lines=lines,
        later_seasons=later,
        later_totals={x: sum(line.later.get(x, 0) for line in lines) for x in later},
        trade_exceptions=exceptions,
        sources={k: v for k, v in dates.items() if k in SHEET_SOURCES},
        warnings=warnings,
    )
