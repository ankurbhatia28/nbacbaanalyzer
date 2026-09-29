"""
Hand-asserted facts that no scraped source represents.

Applied *after* scraped data and reported separately, so a correction reads as a
deliberate act rather than blending into the pipeline. Every row carries a
citation; a row that cannot cite a primary source does not belong here.

The motivating case: the NBA forfeited five Clippers first-round picks in
September 2026. Fanspo models ownership and trades but not forfeiture -- proved
by re-scraping 24 days later and getting fresh data that still showed all five
as held. RealGM does distinguish the two, but its robots.txt disallows
anthropic-ai, so it is a human-read reference here rather than a source.
"""

from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[5] / "data" / "overrides" / "pick_overrides.csv"


class OverrideError(ValueError):
    """A malformed override row. Fail loudly: a silent override is worse than none."""


@dataclass(frozen=True, slots=True)
class PickOverride:
    year: int
    round_: int
    original_team: str
    owner_team: str
    action: str
    citation_url: str
    note: str
    asserted_on: str

    @property
    def key(self) -> tuple[int, int, str, str]:
        """
        Origin alone is not enough. "The Indiana 2029 first" also describes
        Indiana's own pick; the fact being asserted is about the one LAC holds.
        """
        return (self.year, self.round_, self.original_team, self.owner_team)


@dataclass
class OverrideReport:
    loaded: list[PickOverride] = field(default_factory=list)
    applied: list[PickOverride] = field(default_factory=list)
    unmatched: list[PickOverride] = field(default_factory=list)

    @property
    def summary(self) -> dict[str, int]:
        return {
            "loaded": len(self.loaded),
            "applied": len(self.applied),
            "unmatched": len(self.unmatched),
        }


SUPPORTED_ACTIONS = {"forfeit"}


def load_pick_overrides(path: Path | None = None) -> list[PickOverride]:
    target = path or DEFAULT_PATH
    if not target.exists():
        return []
    out: list[PickOverride] = []
    with target.open(encoding="utf-8") as handle:
        for line_no, row in enumerate(csv.DictReader(handle), start=2):
            if not row.get("citation_url", "").strip():
                raise OverrideError(
                    f"{target.name}:{line_no} has no citation_url; "
                    "every override must cite a source"
                )
            action = row["action"].strip()
            if action not in SUPPORTED_ACTIONS:
                raise OverrideError(
                    f"{target.name}:{line_no} unsupported action {action!r}; "
                    f"supported: {', '.join(sorted(SUPPORTED_ACTIONS))}"
                )
            out.append(
                PickOverride(
                    year=int(row["year"]),
                    round_=int(row["round"]),
                    original_team=row["original_team"].strip().upper(),
                    owner_team=row["owner_team"].strip().upper(),
                    action=action,
                    citation_url=row["citation_url"].strip(),
                    note=row.get("note", "").strip(),
                    asserted_on=row.get("asserted_on", "").strip(),
                )
            )
    return out


def apply_pick_overrides(conn: sqlite3.Connection, overrides: list[PickOverride]) -> OverrideReport:
    """
    Mark overridden picks in the already-loaded draft_picks table.

    An override that matches nothing is reported rather than ignored: it usually
    means the scraped data changed shape and the assertion is now pointing at
    nothing, which is exactly when you want to hear about it.
    """
    report = OverrideReport(loaded=list(overrides))
    for override in overrides:
        if override.action != "forfeit":
            continue
        cursor = conn.execute(
            "UPDATE draft_picks SET forfeited = 1, "
            "protection_text = COALESCE(protection_text || ' | ', '') || ? "
            "WHERE year = ? AND round = ? AND original_team_key = ? AND owner_team_key = ?",
            (
                f"OVERRIDE forfeit: {override.note} ({override.citation_url})",
                override.year,
                override.round_,
                override.original_team,
                override.owner_team,
            ),
        )
        (report.applied if cursor.rowcount else report.unmatched).append(override)
    return report
