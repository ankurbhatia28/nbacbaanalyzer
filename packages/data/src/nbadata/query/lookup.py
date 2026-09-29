"""
Player lookup (task 2.9).

Returns candidates, never a guess. The model resolving a name from memory is
exactly the recall ADR-001 forbids; an ambiguous name should produce a
clarifying turn rather than a silent pick.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from ..ingest.names import normalise


@dataclass(frozen=True, slots=True)
class PlayerMatch:
    player_key: str
    display_name: str
    bbref_id: str | None
    years_of_service: int | None
    exact: bool


def lookup_player(conn: sqlite3.Connection, name: str, limit: int = 8) -> list[PlayerMatch]:
    key = normalise(name)
    if not key:
        return []

    exact = conn.execute(
        "SELECT player_key, display_name, bbref_id, years_of_service "
        "FROM players WHERE player_key = ?",
        (key,),
    ).fetchall()
    if exact:
        return [
            PlayerMatch(
                r["player_key"], r["display_name"], r["bbref_id"], r["years_of_service"], True
            )
            for r in exact
        ]

    # Substring on the normalised key handles partials ("jokic", "gilgeous").
    rows = conn.execute(
        "SELECT player_key, display_name, bbref_id, years_of_service FROM players "
        "WHERE player_key LIKE ? ORDER BY LENGTH(player_key) LIMIT ?",
        (f"%{key}%", limit),
    ).fetchall()
    if rows:
        return [
            PlayerMatch(
                r["player_key"], r["display_name"], r["bbref_id"], r["years_of_service"], False
            )
            for r in rows
        ]

    # Last resort: surname only, which is where ambiguity usually lives.
    surname = key.split()[-1]
    rows = conn.execute(
        "SELECT player_key, display_name, bbref_id, years_of_service FROM players "
        "WHERE player_key LIKE ? ORDER BY LENGTH(player_key) LIMIT ?",
        (f"%{surname}%", limit),
    ).fetchall()
    return [
        PlayerMatch(r["player_key"], r["display_name"], r["bbref_id"], r["years_of_service"], False)
        for r in rows
    ]
