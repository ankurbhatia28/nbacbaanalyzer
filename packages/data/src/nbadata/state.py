"""
The league database, as the rules engine sees it (Phase 7).

Until this module the engine only ever ran on hand-built fixtures and the eval
corpus: nothing turned a team's rows into a `TeamState`, so a question like
"is this trade legal?" could be answered from the Agreement's text but never
by the engine. This is that bridge, and it is deliberately the only one -- the
trade builder (7.4), the cap sheet (7.5) and any agent tool read teams through
it, so they cannot disagree about what a team holds.

**Every gap in the data stays a gap** (ADR-003). The engine's types were
written expecting more than the sources carry, and each shortfall is mapped to
an explicit unknown rather than a convenient default:

  contract type      not carried by any source         ContractType.UNKNOWN
  guarantee          'unknown' on every row             GuaranteeType.UNKNOWN
  trade kicker, NTC  tri-state columns, all unknown     Maybe.unknown()
  ceiling row, date  SalarySwish gives level only       None
  trade exceptions   no creation date                   not loaded into TeamState

Trade exceptions are left out of `TeamState` because the engine's
`TradeException` needs a creation date no source gives, and nothing in trade
validation reads them yet (non-simultaneous TPE use is task 3.14, still open).
The cap sheet reads them directly instead.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from engine.apron import ApronLevel, CeilingSet, HardCapCeiling
from engine.contract import (
    Contract,
    ContractOption,
    ContractType,
    ContractYear,
    Guarantee,
    GuaranteeType,
    OptionType,
)
from engine.holds import BirdRights, CapHold, HoldKind
from engine.maybe import Maybe
from engine.provenance import Provenance, Source
from engine.roster import RosterState
from engine.season import Season
from engine.team_state import TeamState

from .ingest.load import SEASON

CURRENT_SEASON = SEASON
"""The season the snapshot describes. Later seasons' thresholds are projections."""


class MissingDataError(LookupError):
    """The database does not hold what was asked for. Raised, never defaulted."""


@dataclass(frozen=True, slots=True)
class Team:
    key: str
    name: str


def teams(conn: sqlite3.Connection) -> list[Team]:
    return [Team(k, n) for k, n in conn.execute("SELECT team_key, name FROM teams ORDER BY name")]


def team(conn: sqlite3.Connection, team_key: str) -> Team:
    row = conn.execute(
        "SELECT team_key, name FROM teams WHERE team_key = ?", (team_key,)
    ).fetchone()
    if row is None:
        raise MissingDataError(f"no team {team_key!r}")
    return Team(row[0], row[1])


def seasons(conn: sqlite3.Connection) -> list[str]:
    return [s for (s,) in conn.execute("SELECT season_id FROM seasons ORDER BY season_id")]


def season(conn: sqlite3.Connection, season_id: str = CURRENT_SEASON) -> Season:
    row = conn.execute(
        "SELECT salary_cap, tax_level, first_apron, second_apron, non_taxpayer_mle, "
        "taxpayer_mle, room_mle, bi_annual_exception, source FROM seasons WHERE season_id = ?",
        (season_id,),
    ).fetchone()
    if row is None:
        raise MissingDataError(f"no season {season_id!r}")
    values = list(row[:8])
    if any(v is None for v in values):
        # A threshold the engine compares against cannot be guessed.
        raise MissingDataError(f"season {season_id} is missing a threshold")
    cap, tax, apron1, apron2, nt_mle, t_mle, room_mle, bae = (int(v) for v in values)
    return Season(
        season_id=season_id,
        salary_cap=cap,
        tax_level=tax,
        first_apron=apron1,
        second_apron=apron2,
        non_taxpayer_mle=nt_mle,
        taxpayer_mle=t_mle,
        room_mle=room_mle,
        bi_annual_exception=bae,
        provenance=_provenance(conn, str(row[8])),
    )


# -- mapping ----------------------------------------------------------------


def _date(value: str | None) -> date | None:
    """ISO, Basketball-Reference's "October 21, 2024", or Spotrac's "7/6/2026"."""
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _maybe[T](state: str | None, value: T | None) -> Maybe[T]:
    if state == "known" and value is not None:
        return Maybe.known(value)
    if state == "absent":
        return Maybe.absent()
    return Maybe.unknown()


def _source(name: str) -> Source:
    try:
        return Source(name.split(",")[0])
    except ValueError:
        return Source.DERIVED


def _provenance(conn: sqlite3.Connection, source: str, as_of: str | None = None) -> Provenance:
    from .query.provenance import source_dates

    when = _date(as_of) or _date(source_dates(conn).get(source.split(",")[0]))
    return Provenance(_source(source), when)


_GUARANTEE = {g.value: g for g in GuaranteeType}
_OPTION = {o.value: o for o in OptionType}


def _contracts(conn: sqlite3.Connection, team_key: str) -> list[Contract]:
    rows = conn.execute(
        """
        SELECT c.contract_id, c.player_key, c.signed_date,
               c.trade_kicker_state, c.trade_kicker_value,
               c.no_trade_clause_state, c.no_trade_clause_value, c.source, c.as_of,
               y.season_id, y.cap_figure, y.guarantee_kind, y.guarantee_amount,
               y.guarantee_date, y.option_kind, y.option_date, y.option_value
        FROM contracts c JOIN contract_years y ON y.contract_id = c.contract_id
        WHERE c.team_key = ?
        ORDER BY c.contract_id, y.season_id
        """,
        (team_key,),
    ).fetchall()
    by_id: dict[int, list[Any]] = {}
    for row in rows:
        by_id.setdefault(int(row[0]), []).append(row)

    out: list[Contract] = []
    for group in by_id.values():
        first = group[0]
        years = tuple(
            ContractYear(
                season_id=str(r[9]),
                cap_figure=int(r[10]),
                guarantee=Guarantee(
                    _GUARANTEE.get(str(r[11]), GuaranteeType.UNKNOWN),
                    amount=int(r[12]) if r[12] is not None else None,
                    guarantee_date=_date(r[13]),
                ),
                option=ContractOption(
                    _OPTION[str(r[14])],
                    decision_date=_date(r[15]),
                    value=int(r[16]) if r[16] is not None else None,
                )
                if r[14] in _OPTION
                else None,
            )
            for r in group
        )
        kicker = first[4]
        ntc = first[6]
        out.append(
            Contract(
                player_id=str(first[1]),
                team_id=team_key,
                contract_type=ContractType.UNKNOWN,
                years=years,
                signed_date=_date(first[2]),
                trade_kicker_pct=_maybe(
                    first[3],
                    float(kicker) if kicker is not None else None,
                ),
                no_trade_clause=_maybe(
                    first[5],
                    bool(ntc) if ntc is not None else None,
                ),
                provenance=_provenance(conn, str(first[7]), first[8]),
            )
        )
    return out


_BIRD = {
    "Bird": BirdRights.FULL,
    "Restricted Bird": BirdRights.FULL,
    "Early Bird": BirdRights.EARLY,
    "Non-Bird": BirdRights.NON,
    "Restricted Non-Bird": BirdRights.NON,
}


def hold_kind(label: str | None) -> HoldKind:
    """
    Fanspo's right-type label, as the hold it is.

    Restricted free agents are held as qualifying offers, because that is how
    they count toward the aprons (Art. VII §2(e)(1)(v)). "Draft Pick" is
    ambiguous -- Fanspo uses it for second-round rights and, oddly, for some
    veterans -- but every non-QO hold is excluded from the aprons alike, so the
    ambiguity cannot change an apron answer.
    """
    if label and label.startswith("Restricted"):
        return HoldKind.QUALIFYING_OFFER
    if label in ("1st Round Pick", "Draft Pick"):
        return HoldKind.DRAFT_PICK
    if label == "Two-Way":
        return HoldKind.TWO_WAY
    return HoldKind.FREE_AGENT


def _holds(conn: sqlite3.Connection, team_key: str, season_id: str) -> list[CapHold]:
    rows = conn.execute(
        "SELECT player_key, amount, bird_rights, qualifying_offer, source, as_of "
        "FROM cap_holds WHERE team_key = ? AND (season_id = ? OR season_id IS NULL)",
        (team_key, season_id),
    ).fetchall()
    return [
        CapHold(
            kind=hold_kind(label),
            amount=int(amount),
            player_id=player,
            description=label,
            bird_rights=_BIRD.get(label or "", BirdRights.NONE),
            # Fanspo writes 0 for "no qualifying offer", which is not a $0 offer.
            qualifying_offer=int(qo) if qo else None,
            provenance=_provenance(conn, str(source), as_of),
        )
        for player, amount, label, qo, source, as_of in rows
    ]


def _ceilings(conn: sqlite3.Connection, team_key: str, season_id: str) -> CeilingSet:
    out = CeilingSet()
    for level, detail, category in conn.execute(
        "SELECT apron_level, trigger_detail, trigger_category FROM hard_cap_ceilings "
        "WHERE team_key = ? AND season_id = ?",
        (team_key, season_id),
    ):
        out.add(
            HardCapCeiling(
                row=None,
                level=ApronLevel(level),
                effective_date=None,
                season_id=season_id,
                source_transaction=" — ".join(str(p) for p in (category, detail) if p),
            )
        )
    return out


def team_state(
    conn: sqlite3.Connection, team_key: str, season_id: str = CURRENT_SEASON
) -> TeamState:
    """One team's position for one season, as the engine needs it."""
    team(conn, team_key)  # raises MissingDataError for an unknown team
    contracts = _contracts(conn, team_key)
    standard = sum(1 for c in contracts if c.cap_figure(season_id) > 0)
    return TeamState(
        team_id=team_key,
        season=season(conn, season_id),
        contracts=contracts,
        cap_holds=_holds(conn, team_key, season_id),
        ceilings=_ceilings(conn, team_key, season_id),
        roster=RosterState(standard_count=standard),
        provenance=_provenance(conn, "bbref_contracts"),
    )


def player_names(conn: sqlite3.Connection, keys: list[str]) -> dict[str, str]:
    """Display names for player keys, so nothing shown to a reader is a join key."""
    if not keys:
        return {}
    marks = ",".join("?" * len(keys))
    rows = conn.execute(
        f"SELECT player_key, display_name FROM players WHERE player_key IN ({marks})", keys
    )
    return {k: n for k, n in rows}
