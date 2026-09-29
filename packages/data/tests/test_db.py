"""Schema shape, and the read-only guarantee ADR-004 depends on."""

import sqlite3
from pathlib import Path

import pytest

from nbadata.db import build, open_readonly

EXPECTED_TABLES = {
    "seasons",
    "teams",
    "players",
    "contracts",
    "contract_years",
    "cap_holds",
    "draft_picks",
    "trade_exceptions",
    "hard_cap_ceilings",
    "awards",
    "disagreements",
    "ingest_meta",
}


@pytest.fixture
def db(tmp_path: Path) -> Path:
    path = tmp_path / "t.db"
    build(path).close()
    return path


def test_schema_has_the_expected_tables(db):
    conn = sqlite3.connect(db)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert names >= EXPECTED_TABLES


def test_runtime_connection_rejects_writes(db):
    """The serving app must not be able to write to the league database."""
    conn = open_readonly(db)
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("INSERT INTO teams VALUES ('XXX','X',NULL,NULL,NULL)")


def test_build_replaces_an_existing_database(db):
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO teams VALUES ('AAA','A',NULL,NULL,NULL)")
    conn.commit()
    conn.close()
    build(db).close()  # rebuild, not migrate
    conn = sqlite3.connect(db)
    assert conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0] == 0


def test_tri_state_columns_exist_as_pairs(db):
    """A nullable column alone would erase absent vs unknown (ADR-003)."""
    conn = sqlite3.connect(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(contracts)")}
    for field in ("trade_kicker", "no_trade_clause"):
        assert f"{field}_state" in cols
        assert f"{field}_value" in cols
