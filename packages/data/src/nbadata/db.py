"""
SQLite schema (task 2.1).

The database is a **build artifact opened read-only at runtime** (ADR-004), so
there are no migrations: ingest drops and rebuilds. Every table carries source
and as_of columns, because the dataset is a set of point-in-time observations
from six sources rather than one coherent snapshot -- the Spotrac rows alone
span thirteen months.

Tri-state fields (ADR-003) are stored as a pair: `<field>_state` in
(known, absent, unknown) plus `<field>_value`. A nullable column alone would
erase the difference between absent and unknown.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE seasons (
    season_id           TEXT PRIMARY KEY,
    salary_cap          INTEGER NOT NULL,
    tax_level           INTEGER NOT NULL,
    first_apron         INTEGER,
    second_apron        INTEGER,
    non_taxpayer_mle    INTEGER,
    taxpayer_mle        INTEGER,
    room_mle            INTEGER,
    bi_annual_exception INTEGER,
    source              TEXT NOT NULL
);

CREATE TABLE teams (
    team_key     TEXT PRIMARY KEY,   -- bbref abbreviation, e.g. MIL
    name         TEXT NOT NULL,
    fanspo_id    TEXT,
    conference   TEXT,
    division     TEXT
);

CREATE TABLE players (
    player_key       TEXT PRIMARY KEY,  -- normalised name; the cross-source join key
    display_name     TEXT NOT NULL,
    bbref_id         TEXT UNIQUE,
    nba_id           TEXT UNIQUE,
    years_of_service INTEGER,
    birth_date       TEXT,
    source           TEXT,
    as_of            TEXT
);
CREATE INDEX idx_players_bbref ON players(bbref_id);

CREATE TABLE contracts (
    contract_id            INTEGER PRIMARY KEY,
    player_key             TEXT NOT NULL REFERENCES players(player_key),
    team_key               TEXT,
    contract_type          TEXT,
    signed_date            TEXT,
    trade_kicker_state     TEXT NOT NULL DEFAULT 'unknown',
    trade_kicker_value     REAL,
    no_trade_clause_state  TEXT NOT NULL DEFAULT 'unknown',
    no_trade_clause_value  INTEGER,
    source                 TEXT NOT NULL,
    as_of                  TEXT
);
CREATE INDEX idx_contracts_player ON contracts(player_key);
CREATE INDEX idx_contracts_team ON contracts(team_key);

CREATE TABLE contract_years (
    contract_id      INTEGER NOT NULL REFERENCES contracts(contract_id),
    season_id        TEXT NOT NULL,
    cap_figure       INTEGER NOT NULL,
    -- 'unknown' until a source supplies it. Basketball-Reference marks
    -- guarantee status with cell styling the scraper does not capture, so
    -- defaulting to 'full' asserted something we had never read (ADR-003).
    guarantee_kind   TEXT NOT NULL DEFAULT 'unknown',
    guarantee_amount INTEGER,
    guarantee_date   TEXT,
    option_kind      TEXT,
    option_date      TEXT,
    option_value     INTEGER,
    PRIMARY KEY (contract_id, season_id)
);
CREATE INDEX idx_cy_season ON contract_years(season_id);

CREATE TABLE dead_money (
    dead_id     INTEGER PRIMARY KEY,
    team_key    TEXT NOT NULL,
    player_key  TEXT,
    amount      INTEGER NOT NULL,
    season_id   TEXT NOT NULL,
    source      TEXT NOT NULL,
    as_of       TEXT
);
CREATE INDEX idx_dead_team ON dead_money(team_key);

CREATE TABLE cap_holds (
    hold_id     INTEGER PRIMARY KEY,
    team_key    TEXT NOT NULL,
    player_key  TEXT REFERENCES players(player_key),
    kind        TEXT NOT NULL,
    amount      INTEGER NOT NULL,
    bird_rights TEXT,
    qualifying_offer INTEGER,
    season_id   TEXT,
    source      TEXT NOT NULL,
    as_of       TEXT
);
CREATE INDEX idx_holds_team ON cap_holds(team_key);
CREATE INDEX idx_holds_bird ON cap_holds(bird_rights);

CREATE TABLE draft_picks (
    pick_id           INTEGER PRIMARY KEY,
    year              INTEGER NOT NULL,
    round             INTEGER NOT NULL,
    original_team_key TEXT,
    owner_team_key    TEXT,
    forfeited         INTEGER NOT NULL DEFAULT 0,
    protection_text   TEXT,
    source            TEXT NOT NULL,
    as_of             TEXT
);
CREATE INDEX idx_picks_owner ON draft_picks(owner_team_key, year, round);

CREATE TABLE trade_exceptions (
    tpe_id       INTEGER PRIMARY KEY,
    team_key     TEXT NOT NULL,
    amount       INTEGER NOT NULL,
    available    INTEGER,
    created      TEXT,
    expires      TEXT,
    kind         TEXT,
    reason       TEXT,
    source       TEXT NOT NULL,
    as_of        TEXT
);
CREATE INDEX idx_tpe_team ON trade_exceptions(team_key);

CREATE TABLE hard_cap_ceilings (
    ceiling_id       INTEGER PRIMARY KEY,
    team_key         TEXT NOT NULL,
    apron_level      TEXT NOT NULL,          -- first_apron | second_apron
    restriction_row  TEXT,                   -- A..K, where we can map it
    trigger_category TEXT,
    trigger_detail   TEXT,
    season_id        TEXT,
    source           TEXT NOT NULL
);
CREATE INDEX idx_ceilings_team ON hard_cap_ceilings(team_key);

CREATE TABLE awards (
    award_id    INTEGER PRIMARY KEY,
    player_key  TEXT REFERENCES players(player_key),
    bbref_id    TEXT,
    season_id   TEXT NOT NULL,
    award       TEXT NOT NULL,
    tier        TEXT,
    source      TEXT NOT NULL
);
CREATE INDEX idx_awards_player ON awards(player_key, season_id);

CREATE TABLE disagreements (
    id          INTEGER PRIMARY KEY,
    field       TEXT NOT NULL,
    subject     TEXT NOT NULL,
    chosen      TEXT NOT NULL,   -- winning source
    chosen_value TEXT,
    others      TEXT NOT NULL    -- json: {source: value}
);

CREATE TABLE ingest_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def build(path: Path | str) -> sqlite3.Connection:
    """Create a fresh database. Existing file is replaced -- ingest is a rebuild."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    conn = sqlite3.connect(target)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def open_readonly(path: Path | str) -> sqlite3.Connection:
    """
    How the serving application opens it (ADR-004): read-only.

    `check_same_thread=False` because ADR-004 makes this a read-only build
    artifact -- nothing at runtime writes to it, so there is no write
    contention for that guard to protect against. Python reports
    `sqlite3.threadsafety == 3` (serialized), meaning connections may be shared
    across threads. Streaming (6.9) runs the agent loop on a worker thread
    while the caller reads progress, and without this it fails with
    "SQLite objects created in a thread can only be used in that same thread".
    """
    uri = f"file:{Path(path).resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
