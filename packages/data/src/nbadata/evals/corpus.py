"""
The eval corpus: real trades, parsed into something the engine can be run against.

Every completed trade was legal when it happened, which makes the corpus
self-labelling — no annotation, no judgement calls. A real trade the engine
rejects is an engine bug, not a disputed case.

Each team's own salary movement comes from two figures the source publishes per
leg:

    incoming = Cap Hit Sum
    outgoing = Cap Hit Sum - Cap Hit Change

That derivation is checked rather than assumed: within a trade, total incoming
must equal total outgoing, and a case that fails to balance is excluded rather
than evaluated on numbers we do not trust.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

from ..ingest.teams import from_display

DEFAULT_LEGS = (
    Path(__file__).resolve().parents[5] / "scraper" / "out" / "salaryswish_trade_legs.csv"
)

CAP_HIT_SUM = re.compile(r"Cap Hit Sum:\s*\$?(-?[\d,]+)")
CAP_HIT_CHANGE = re.compile(r"Cap Hit Change:\s*([+-])\$?([\d,]+)")
CASH = re.compile(r"Cash:\s*\$?([\d,]+)")
TPE_GENERATED = re.compile(r"Trade Exceptions Generated:")
PICK = re.compile(r"(20\d\d)\s+(1st|2nd)\s+round pick")
PLAYER_SALARY = re.compile(r"·\s*\$([\d,]+)")
FROM_BLOCK = re.compile(
    r"From ([A-Z]{3}):(.*?)(?=From [A-Z]{3}:|Cap Hit Sum|Trade Exceptions|$)", re.S
)
TEAM_CODE = re.compile(r"\b([A-Z]{3})\b")


def _money(text: str) -> int:
    return int(text.replace(",", ""))


@dataclass(frozen=True, slots=True)
class Leg:
    team: str
    incoming: int
    outgoing: int
    cash_received: int
    picks_acquired: int
    generated_tpe: bool
    player_count: int
    incoming_salaries: tuple[int, ...] = ()
    """Individual acquired contracts, in the order the source lists them."""
    outgoing_salaries: tuple[int, ...] = ()
    """
    Individual contracts sent, reconstructed from what the counterparties
    acquired. Needed because Art. VII 6(j) lets a team split its outgoing
    players across several exceptions, and a single aggregate figure cannot
    express that.
    """

    @property
    def net(self) -> int:
        return self.incoming - self.outgoing

    @property
    def is_aggregating(self) -> bool:
        """Two or more outgoing contracts changes which exception applies."""
        return len(self.outgoing_salaries) >= 2

    @property
    def outgoing_reconstructed(self) -> bool:
        """
        Whether the per-player outgoing figures add up to the aggregate. When
        they do not, the split is unreliable and the leg should be evaluated on
        the aggregate alone.
        """
        return bool(self.outgoing_salaries) and sum(self.outgoing_salaries) == self.outgoing


@dataclass
class TradeCase:
    trade_id: int
    date: str
    legs: list[Leg] = field(default_factory=list)
    balanced: bool = True
    aggregating_teams: set[str] = field(default_factory=set)

    @property
    def season_id(self) -> str:
        """A Salary Cap Year runs July 1 to June 30."""
        year, month = int(self.date[:4]), int(self.date[5:7])
        start = year if month >= 7 else year - 1
        return f"{start}-{start + 1}"

    @property
    def team_count(self) -> int:
        return len(self.legs)

    def leg_for(self, team: str) -> Leg | None:
        return next((leg for leg in self.legs if leg.team == team), None)


def _incoming_by_source(detail: str) -> dict[str | None, list[int]]:
    """
    Acquired contracts grouped by the team they came from.

    Multi-team trades prefix each block with "From XXX:"; two-team trades do
    not, because the counterparty is unambiguous. `None` keys the unattributed
    case, which `load` resolves from the other leg.
    """
    blocks = FROM_BLOCK.findall(detail)
    if blocks:
        return {code: [_money(m) for m in PLAYER_SALARY.findall(body)] for code, body in blocks}
    head = detail.split("Cap Hit Sum")[0]
    return {None: [_money(m) for m in PLAYER_SALARY.findall(head)]}


def _parse_leg(team: str, detail: str, outgoing_players: int) -> Leg | None:
    sum_match = CAP_HIT_SUM.search(detail)
    change_match = CAP_HIT_CHANGE.search(detail)
    if not sum_match or not change_match:
        return None
    incoming = _money(sum_match.group(1))
    change = (1 if change_match.group(1) == "+" else -1) * _money(change_match.group(2))
    cash = CASH.search(detail)
    head = detail.split("Cap Hit Sum")[0]
    return Leg(
        team=team,
        incoming=incoming,
        outgoing=incoming - change,
        cash_received=_money(cash.group(1)) if cash else 0,
        picks_acquired=len(PICK.findall(detail)),
        generated_tpe=bool(TPE_GENERATED.search(detail)),
        player_count=len(PLAYER_SALARY.findall(head)),
        incoming_salaries=tuple(_money(m) for m in PLAYER_SALARY.findall(head)),
    )


def _reconstruct_outgoing(case: TradeCase, details: dict[str, str]) -> None:
    """
    Fill in each team's outgoing contracts from what the others acquired.

    One team's outgoing players are exactly what every counterparty acquired
    from it. Two-team trades need no attribution -- the other leg's whole
    acquisition came from this team. Multi-team trades carry "From XXX:"
    prefixes, which map back through the team code.
    """
    codes = {leg.team: from_display(leg.team) for leg in case.legs}
    for index, leg in enumerate(case.legs):
        code = codes.get(leg.team)
        sent: list[int] = []
        for other in case.legs:
            if other.team == leg.team:
                continue
            by_source = _incoming_by_source(details.get(other.team, ""))
            if None in by_source:
                # Unattributed: only unambiguous in a two-team trade.
                if len(case.legs) == 2:
                    sent.extend(by_source[None])
            elif code and code in by_source:
                sent.extend(by_source[code])
        case.legs[index] = replace(leg, outgoing_salaries=tuple(sent))


def load(path: Path | None = None, *, min_season: str = "2023-2024") -> list[TradeCase]:
    """
    Build cases from scraped legs, keeping only trades under the 2023 CBA.

    Earlier trades are governed by the previous agreement, which this engine
    does not model (D7), so validating against them would test the wrong rules.
    """
    source = path or DEFAULT_LEGS
    if not source.exists():
        return []
    grouped: dict[int, list[dict[str, str]]] = {}
    with source.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if not row.get("date"):
                continue
            grouped.setdefault(int(row["trade_id"]), []).append(row)

    cases: list[TradeCase] = []
    for trade_id, rows in sorted(grouped.items()):
        case = TradeCase(trade_id=trade_id, date=rows[0]["date"])
        if case.season_id < min_season:
            continue
        details: dict[str, str] = {}
        for row in rows:
            leg = _parse_leg(row["team"], row["detail"], 0)
            if leg is not None:
                case.legs.append(leg)
                details[leg.team] = row["detail"]
        if not case.legs:
            continue

        _reconstruct_outgoing(case, details)

        total_in = sum(leg.incoming for leg in case.legs)
        total_out = sum(leg.outgoing for leg in case.legs)
        case.balanced = total_in == total_out
        cases.append(case)
    return cases
