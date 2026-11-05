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

-- One row per provider. For legacy rows the secret is encrypted (see crypto.py)
-- and `credential_source` is NULL (treated as 'db'). P1 adds the file-backed
-- path: when a Mini-side launcher injects the key via a runtime secret file
-- (AEC_GARMIN_API_KEY_FILE), credential_source='file', secret_enc IS NULL,
-- and file_path records the mount. The DB never stores the key in that mode.
CREATE TABLE IF NOT EXISTS provider_credentials (
    provider TEXT PRIMARY KEY,
    secret_enc BLOB,
    updated_at TEXT NOT NULL,
    validated_at TEXT,
    credential_source TEXT,
    file_path TEXT
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

-- P2 (schema v3): coach-maths layer.
--
-- Sport keys (Garmin's typeKey strings) mapped to a small set of families the
-- maths dispatches on. One row per sport key; populated lazily from activities.
CREATE TABLE IF NOT EXISTS sports (
    key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    family TEXT NOT NULL,
    load_method_primary TEXT NOT NULL,
    load_method_fallback TEXT,
    zones_axes_json TEXT,
    created_at TEXT NOT NULL
);

-- Per-activity load; recomputed from the activity + current thresholds.
CREATE TABLE IF NOT EXISTS activity_load (
    activity_id INTEGER PRIMARY KEY REFERENCES activities(id) ON DELETE CASCADE,
    family TEXT NOT NULL,
    trimp REAL,
    tss REAL,
    method TEXT NOT NULL,
    inputs_json TEXT,
    computed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_load_family ON activity_load(family);

-- Daily aggregated load + PMC (CTL/ATL/TSB) and ACWR.
CREATE TABLE IF NOT EXISTS training_load_day (
    day TEXT PRIMARY KEY,
    trimp REAL NOT NULL DEFAULT 0,
    tss REAL NOT NULL DEFAULT 0,
    ctl REAL,
    atl REAL,
    tsb REAL,
    acwr REAL,
    computed_at TEXT NOT NULL
);

-- Per-family daily load + per-family PMC (the UI shows the sport split).
CREATE TABLE IF NOT EXISTS training_load_day_family (
    day TEXT NOT NULL,
    family TEXT NOT NULL,
    trimp REAL NOT NULL DEFAULT 0,
    tss REAL NOT NULL DEFAULT 0,
    ctl REAL,
    atl REAL,
    tsb REAL,
    PRIMARY KEY (day, family)
);

-- Daily subjective check-in (one row per day; last write wins).
CREATE TABLE IF NOT EXISTS checkins (
    day TEXT PRIMARY KEY,
    overall INTEGER,
    legs INTEGER,
    sleep_feel INTEGER,
    stress INTEGER,
    alcohol_units REAL,
    ill INTEGER,
    note TEXT,
    created_at TEXT NOT NULL
);

-- Composite readiness 0-100 with its sub-parts kept so the UI can show "why".
CREATE TABLE IF NOT EXISTS readiness_day (
    day TEXT PRIMARY KEY,
    score INTEGER,
    band TEXT,
    hrv_part REAL,
    sleep_part REAL,
    rhr_part REAL,
    load_part REAL,
    checkin_part REAL,
    inputs_json TEXT,
    computed_at TEXT NOT NULL
);

-- Ride/run/swim/strength metrics per activity (NP/IF, EF, decoupling, etc).
-- One row per activity; sparse columns per family.
CREATE TABLE IF NOT EXISTS ride_metrics (
    activity_id INTEGER PRIMARY KEY REFERENCES activities(id) ON DELETE CASCADE,
    family TEXT NOT NULL,
    np REAL,
    if_ REAL,
    tss REAL,
    hrtss REAL,
    rtss REAL,
    stss REAL,
    rpetss REAL,
    ef REAL,
    pacing_cv REAL,
    fade_pct REAL,
    decoupling_pct REAL,
    ftp_at_time REAL,
    lthr_at_time INTEGER,
    threshold_pace_at_time REAL,
    css_at_time REAL,
    computed_at TEXT NOT NULL
);

-- Time spent in each zone on each axis (hr | power | pace | stroke).
CREATE TABLE IF NOT EXISTS time_in_zone (
    activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    axis TEXT NOT NULL,
    zone INTEGER NOT NULL,
    seconds REAL NOT NULL,
    PRIMARY KEY (activity_id, axis, zone)
);

-- Detected climbs within an activity (for trail/bike).
CREATE TABLE IF NOT EXISTS climbs (
    activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    start_offset_s REAL NOT NULL,
    end_offset_s REAL NOT NULL,
    length_m REAL NOT NULL,
    avg_gradient REAL,
    max_gradient REAL,
    vam REAL,
    PRIMARY KEY (activity_id, idx)
);

-- Mean-maximum power curve (bike + run-power).
CREATE TABLE IF NOT EXISTS mean_max_power (
    activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    window_s INTEGER NOT NULL,
    watts REAL NOT NULL,
    PRIMARY KEY (activity_id, window_s)
);

-- Mean-maximum pace curve (run/swim).
CREATE TABLE IF NOT EXISTS mean_max_pace (
    activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    window_s INTEGER NOT NULL,
    metres_per_s REAL NOT NULL,
    PRIMARY KEY (activity_id, window_s)
);

-- 100 m / lap splits for swim.
CREATE TABLE IF NOT EXISTS swim_splits (
    activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    distance_m REAL,
    time_s REAL,
    strokes INTEGER,
    swolf REAL,
    PRIMARY KEY (activity_id, idx)
);

-- Automatic interval detection (work / rest segments with averages).
CREATE TABLE IF NOT EXISTS detected_intervals (
    activity_id INTEGER NOT NULL REFERENCES activities(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    start_offset_s REAL NOT NULL,
    end_offset_s REAL NOT NULL,
    work_or_rest TEXT NOT NULL,
    avg_hr REAL,
    avg_power REAL,
    avg_pace REAL,
    PRIMARY KEY (activity_id, idx)
);

-- Running VDOT: a running state we update slowly (±0.5 per confirmed event).
CREATE TABLE IF NOT EXISTS vdot_state (
    day TEXT PRIMARY KEY,
    vdot REAL NOT NULL,
    source TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS vdot_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    delta REAL NOT NULL,
    reason TEXT NOT NULL,
    sessions_json TEXT
);

-- Threshold staleness detector; never overwrites stored user values.
CREATE TABLE IF NOT EXISTS thresholds_staleness (
    sport_key TEXT PRIMARY KEY,
    stored REAL,
    suggested REAL,
    evidence_json TEXT,
    computed_at TEXT NOT NULL
);

-- P2b: life-data feeds. All pure-pull, idempotent.
-- Weather per activity: nearest-hour ERA5 archive from Open-Meteo.
CREATE TABLE IF NOT EXISTS activity_weather (
    activity_id INTEGER PRIMARY KEY REFERENCES activities(id) ON DELETE CASCADE,
    temp_c REAL,
    feels_like_c REAL,
    dew_point_c REAL,
    humidity_pct REAL,
    wind_m_s REAL,
    precip_mm REAL,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);

-- Weather daily context (one row per day).
CREATE TABLE IF NOT EXISTS weather_day (
    day TEXT PRIMARY KEY,
    temp_min_c REAL,
    temp_max_c REAL,
    apparent_mean_c REAL,
    dew_point_mean_c REAL,
    humidity_mean_pct REAL,
    precip_mm REAL,
    fetched_at TEXT NOT NULL
);

-- Calendar read-only mirror from an ICS URL.
CREATE TABLE IF NOT EXISTS calendar_events (
    id TEXT PRIMARY KEY,
    day TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    summary TEXT,
    is_travel INTEGER NOT NULL DEFAULT 0,
    is_busy INTEGER NOT NULL DEFAULT 0,
    source TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_calendar_events_day ON calendar_events(day);

-- Home Assistant history (long-term, bucketed per entity).
CREATE TABLE IF NOT EXISTS ha_series (
    entity_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    value REAL,
    PRIMARY KEY (entity_id, ts)
);
CREATE INDEX IF NOT EXISTS idx_ha_series_ts ON ha_series(ts);

CREATE TABLE IF NOT EXISTS ha_daily (
    day TEXT PRIMARY KEY,
    bedroom_temp_c_night REAL,
    bedroom_rh_pct_night REAL,
    bed_in_time TEXT,
    bed_out_time TEXT,
    wake_time TEXT,
    computed_at TEXT NOT NULL
);

-- Life signal rollup (derived).
CREATE TABLE IF NOT EXISTS life_signal_day (
    day TEXT PRIMARY KEY,
    travel INTEGER NOT NULL DEFAULT 0,
    busy INTEGER NOT NULL DEFAULT 0,
    alcohol_units REAL,
    sick INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    computed_at TEXT NOT NULL
);

-- Correlations (association, not cause). One row per (y, x, lag_days).
CREATE TABLE IF NOT EXISTS correlations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    y TEXT NOT NULL,
    x TEXT NOT NULL,
    lag_days INTEGER NOT NULL,
    n INTEGER NOT NULL,
    rho REAL,
    ci_low REAL,
    ci_high REAL,
    method TEXT NOT NULL,
    p_approx REAL,
    computed_at TEXT NOT NULL,
    UNIQUE (y, x, lag_days)
);

-- Power-vs-HR disagreement per ride.
CREATE TABLE IF NOT EXISTS ride_disagreement (
    activity_id INTEGER PRIMARY KEY REFERENCES activities(id) ON DELETE CASCADE,
    disagreement_score REAL NOT NULL,
    cause TEXT,
    confidence REAL,
    evidence_json TEXT,
    computed_at TEXT NOT NULL
);

-- Nightly routine profile. One row per nightly run; latest = current.
CREATE TABLE IF NOT EXISTS routine_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    computed_at TEXT NOT NULL,
    profile_json TEXT NOT NULL
);

-- Daily suggestion with feedback and matched actual activity.
CREATE TABLE IF NOT EXISTS suggestion_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    primary_json TEXT NOT NULL,
    alternative_json TEXT,
    user_action TEXT,
    actual_activity_id INTEGER REFERENCES activities(id) ON DELETE SET NULL,
    actual_similarity REAL,
    recorded_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_suggestion_history_day ON suggestion_history(day);

-- P3: coach / LLM transcript. One row per message in a tool-calling turn.
CREATE TABLE IF NOT EXISTS coach_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    created_at TEXT NOT NULL,
    model TEXT NOT NULL,
    role TEXT NOT NULL,              -- system | user | assistant | tool
    text TEXT,
    tool_calls_json TEXT,
    numbers_json TEXT,
    duration_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_coach_messages_created ON coach_messages(created_at);
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


SCHEMA_VERSION = 5  # bump when a migration is added; stored in PRAGMA user_version


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
        # P1 (schema v2): provider_credentials gains a credential_source + file_path
        # so a key injected as a runtime secret file can leave secret_enc NULL.
        # Existing rows (secret_enc NOT NULL) are implicitly credential_source='db'.
        _add_column(conn, "provider_credentials", "credential_source", "credential_source TEXT")
        _add_column(conn, "provider_credentials", "file_path", "file_path TEXT")
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
    finally:
        conn.close()
