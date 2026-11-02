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

-- Fastest time over standard distances within each running activity (see efforts.py).
CREATE TABLE IF NOT EXISTS best_efforts (
    activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    distance_m REAL NOT NULL,
    time_s REAL NOT NULL,
    start_offset_s REAL NOT NULL,
    avg_hr REAL,
    ascent_m REAL,
    gap_s REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (activity_id, distance_m)
);
-- Same as best_efforts, but on a grade-adjusted axis: distance_m is FLAT-EQUIVALENT distance and
-- covered_m is the real distance run in that stretch (see efforts.equivalent_distance).
CREATE TABLE IF NOT EXISTS best_efforts_gap (
    activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    distance_m REAL NOT NULL,
    time_s REAL NOT NULL,
    start_offset_s REAL NOT NULL,
    avg_hr REAL,
    ascent_m REAL,
    gap_s REAL NOT NULL DEFAULT 0,
    covered_m REAL NOT NULL,
    PRIMARY KEY (activity_id, distance_m)
);
-- Laps (what Garmin Connect calls splits): automatic 1 km laps, manual laps or workout steps, from the FIT file.
CREATE TABLE IF NOT EXISTS laps (
    activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    start_t INTEGER,
    elapsed_s REAL, timer_s REAL, distance_m REAL,
    avg_speed REAL, max_speed REAL,
    avg_hr REAL, max_hr REAL,
    ascent_m REAL, descent_m REAL,
    avg_cadence REAL, avg_power REAL,
    trigger TEXT, intensity TEXT,
    PRIMARY KEY (activity_id, idx)
) WITHOUT ROWID;
-- Which activities have had their laps read from the stored FIT file (so an activity with none is not rescanned forever).
CREATE TABLE IF NOT EXISTS lap_scan (
    activity_id INTEGER PRIMARY KEY REFERENCES activities(id) ON DELETE CASCADE,
    scanned_at TEXT NOT NULL,
    version INTEGER NOT NULL,
    laps INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS effort_scan (
    activity_id INTEGER PRIMARY KEY REFERENCES activities(id) ON DELETE CASCADE,
    scanned_at TEXT NOT NULL,
    version INTEGER NOT NULL
);
-- Activities the athlete has chosen to leave out of predictions.
CREATE TABLE IF NOT EXISTS effort_exclusions (
    activity_id INTEGER PRIMARY KEY REFERENCES activities(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);

-- Peak sustained heart rate per activity (see efforts.hr_peak), for estimating max heart rate.
CREATE TABLE IF NOT EXISTS hr_peaks (
    activity_id INTEGER PRIMARY KEY REFERENCES activities(id) ON DELETE CASCADE,
    peak_hr REAL NOT NULL,
    at_offset_s REAL NOT NULL,
    samples INTEGER NOT NULL
);
-- Activities the athlete says were races (used to check predictions against real results).
CREATE TABLE IF NOT EXISTS race_marks (
    activity_id INTEGER PRIMARY KEY REFERENCES activities(id) ON DELETE CASCADE,
    marked_at TEXT NOT NULL
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
