"""
Where a query's figures came from, and when they were true (task 7.6).

Every query result carries this, because the dataset is a set of
point-in-time observations from six sources rather than one coherent snapshot.
A number shown without an as-of date implies it is current, and for a scraped
snapshot that implication is quietly false.

**Three kinds of date, kept distinct.** A row may carry its own observation
date (Spotrac's archive snapshots). A row from a live page has none, but the
page was read on a known day, so the scrape date stands in -- and is labelled
as a scrape date, because it says when we looked, not when the fact last
changed. A row with neither is reported as undated: unknown is not zero
(ADR-003), and an absent date must not be filled with a plausible one.

Provenance covers every row the query's filters select, not only the rows a
LIMIT kept. That errs wide: a date range that includes a row the answer did
not show is a smaller error than one that omits a row a SUM included.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from enum import StrEnum

from .catalog import Entity
from .compile import where_clause
from .dsl import Query


class Basis(StrEnum):
    ROW = "row"
    """The row's own observation date."""
    SCRAPED = "scraped"
    """No row date; the date the source was read."""
    UNDATED = "undated"
    """Neither. Reported, not guessed."""


@dataclass(frozen=True, slots=True)
class Observed:
    """One source's share of a result, with the dates it was observed."""

    source: str
    rows: int
    basis: Basis
    earliest: str | None = None
    latest: str | None = None

    def describe(self) -> str:
        if self.basis is Basis.UNDATED:
            return f"{self.source}, date unknown ({self.rows} rows)"
        when = self.earliest
        if self.latest != self.earliest:
            when = f"{self.earliest} to {self.latest}"
        verb = "scraped" if self.basis is Basis.SCRAPED else "as of"
        return f"{self.source}, {verb} {when} ({self.rows} rows)"

    def to_json(self) -> dict[str, object]:
        return {
            "source": self.source,
            "rows": self.rows,
            "basis": self.basis.value,
            "earliest": self.earliest,
            "latest": self.latest,
        }


def source_dates(conn: sqlite3.Connection) -> dict[str, str]:
    """Scrape dates the ingest recorded. Empty for a database built before 7.6."""
    try:
        row = conn.execute("SELECT value FROM ingest_meta WHERE key = 'source_dates'").fetchone()
    except sqlite3.OperationalError:
        return {}
    if row is None:
        return {}
    loaded = json.loads(row[0])
    return {str(k): str(v) for k, v in loaded.items()} if isinstance(loaded, dict) else {}


def observe(conn: sqlite3.Connection, query: Query) -> tuple[Observed, ...]:
    """Provenance for the rows `query` selects, one entry per source and basis."""
    entity: Entity = query.validate()
    where_sql, params = where_clause(entity, query)
    src = entity.source_column
    as_of = entity.as_of_column
    dated = f"MIN({as_of}), MAX({as_of}), COUNT({as_of})" if as_of else "NULL, NULL, 0"
    sql = (
        f"SELECT {src}, COUNT(*), {dated}\nFROM {entity.source_sql.strip()}"
        + (f"\nWHERE {where_sql}" if where_sql else "")
        + f"\nGROUP BY {src}\nORDER BY {src}"
    )
    scraped = source_dates(conn)
    out: list[Observed] = []
    for source, total, earliest, latest, with_date in conn.execute(sql, params).fetchall():
        name = str(source)
        if with_date:
            out.append(Observed(name, int(with_date), Basis.ROW, earliest, latest))
        undated = int(total) - int(with_date)
        if not undated:
            continue
        if when := scraped.get(name):
            out.append(Observed(name, undated, Basis.SCRAPED, when, when))
        else:
            out.append(Observed(name, undated, Basis.UNDATED))
    return tuple(out)


@dataclass(frozen=True, slots=True)
class Snapshot:
    """
    The dataset as a whole: when it was built, and when each source was read.

    Shown once per answer, beside the per-figure provenance. The build date
    alone would mislead -- a database built today from a scrape a month old is
    a month old.
    """

    built_at: str | None
    season: str | None
    source_dates: dict[str, str]

    def to_json(self) -> dict[str, object]:
        return {
            "built_at": self.built_at,
            "season": self.season,
            "source_dates": dict(self.source_dates),
        }


def snapshot(conn: sqlite3.Connection) -> Snapshot:
    """Read the dataset's build record. Missing keys stay None, not a default."""
    try:
        meta = dict(conn.execute("SELECT key, value FROM ingest_meta").fetchall())
    except sqlite3.OperationalError:
        meta = {}
    return Snapshot(
        built_at=meta.get("built_at"),
        season=meta.get("season"),
        source_dates=source_dates(conn),
    )
