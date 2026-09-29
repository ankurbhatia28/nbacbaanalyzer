"""Execute a validated query against the read-only database."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .compile import compile_query
from .dsl import Query


@dataclass(frozen=True, slots=True)
class QueryResult:
    """
    Carries the SQL that produced it. Task 7.3 shows this in the UI: a number
    whose derivation cannot be inspected is a number you cannot check.
    """

    columns: list[str]
    rows: list[dict[str, object]]
    sql: str
    params: list[object]

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def scalar(self) -> object | None:
        if not self.rows:
            return None
        return next(iter(self.rows[0].values()))


def run(conn: sqlite3.Connection, query: Query) -> QueryResult:
    sql, params = compile_query(query)
    cursor = conn.execute(sql, params)
    columns = [d[0] for d in cursor.description]
    rows = [dict(zip(columns, r, strict=True)) for r in cursor.fetchall()]
    return QueryResult(columns=columns, rows=rows, sql=sql, params=params)
