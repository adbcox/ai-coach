"""SQLite storage (WAL mode). One short-lived connection per request or job."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);

-- One row per provider. The secret is encrypted (see crypto.py), never plain text.
CREATE TABLE IF NOT EXISTS provider_credentials (
    provider TEXT PRIMARY KEY,
    secret_enc BLOB NOT NULL,
    updated_at TEXT NOT NULL,
    validated_at TEXT
);

-- Every activity is stored with its source and the source's own id, so a second
-- provider can be linked later without migrating data. canonical_id is reserved
-- for cross-source linking/de-duplication (roadmap: "With 2nd provider").
CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    canonical_id INTEGER,
    start_time TEXT NOT NULL,
    sport TEXT,
    name TEXT,
    distance_m REAL,
    duration_s REAL,
    elevation_gain_m REAL,
    avg_hr REAL,
    max_hr REAL,
    summary_json TEXT,
    file_path TEXT,
    has_samples INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    UNIQUE (source, source_id)
);
CREATE INDEX IF NOT EXISTS idx_activities_start ON activities(start_time);

CREATE TABLE IF NOT EXISTS samples (
    activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    t INTEGER NOT NULL,          -- unix seconds
    lat REAL, lon REAL, alt REAL,
    hr INTEGER, cadence INTEGER, power INTEGER,
    speed REAL,                  -- m/s
    dist REAL,                   -- cumulative metres
    PRIMARY KEY (activity_id, t)
) WITHOUT ROWID;

CREATE TABLE IF NOT EXISTS sync_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Raw Garmin wellness payloads (sleep, HRV, Body Battery, stress, HR, SpO2, ...).
-- Stored as received so nothing is lost; the dashboard parses what it needs later.
CREATE TABLE IF NOT EXISTS wellness_raw (
    source TEXT NOT NULL,
    kind TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    is_empty INTEGER NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY (source, kind, start_date, end_date)
);

-- One optional network-share target for scheduled backups. The password is encrypted
-- with the master key like the Garmin key.
CREATE TABLE IF NOT EXISTS backup_target (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    host TEXT NOT NULL,
    port INTEGER NOT NULL DEFAULT 445,
    share TEXT NOT NULL,
    folder TEXT NOT NULL DEFAULT '',
    username TEXT NOT NULL,
    domain TEXT,
    password_enc BLOB NOT NULL,
    interval_minutes INTEGER NOT NULL DEFAULT 1440,
    keep INTEGER NOT NULL DEFAULT 14,
    last_run_at TEXT,
    last_status TEXT,
    last_message TEXT
);

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,        -- running | ok | error
    new_activities INTEGER NOT NULL DEFAULT 0,
    message TEXT
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Each request/job uses its own connection, one thread at a time; FastAPI may set the
    # connection up in one worker thread and use it in another, so allow that.
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


SCHEMA_VERSION = 1  # bump when a migration is added; stored in PRAGMA user_version


def _add_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
    cols = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


def init_db(path: Path) -> None:
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        # upgrades for databases created by earlier versions
        _add_column(conn, "sync_runs", "mode", "mode TEXT")
        _add_column(conn, "sync_runs", "scheduled", "scheduled INTEGER NOT NULL DEFAULT 0")
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
    finally:
        conn.close()
