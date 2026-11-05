"""Threshold staleness — flags when recent efforts beat the stored value.

D1: never overwrites the stored value; just suggests + evidence.
"""

from app import db
from app.coach_maths import sport, staleness
from app.config import Settings


def _mk(tmp_path):
    s = Settings(data_dir=tmp_path, request_delay_s=0)
    db.init_db(s.db_path)
    conn = db.connect(s.db_path)
    sport.seed_sport(conn, "cycling")
    return s, conn


def _ins_mmp(conn, activity_id, start, window_s, watts):
    conn.execute(
        "INSERT INTO activities (id, source, source_id, start_time, sport, name, "
        "created_at) VALUES (?, 'garmin', ?, ?, 'cycling', 'x', '2026-01-01T00:00:00+00:00')",
        (activity_id, str(activity_id), start),
    )
    conn.execute(
        "INSERT INTO mean_max_power (activity_id, window_s, watts) VALUES (?, ?, ?)",
        (activity_id, window_s, watts),
    )


def test_flags_stale_ftp(tmp_path):
    _, conn = _mk(tmp_path)
    conn.execute("INSERT INTO sync_state (key, value) VALUES ('thresholds.ftp', '250')")
    _ins_mmp(conn, 1, "2026-10-30T12:00:00+00:00", 1200, 280)   # new 20-min best
    conn.commit()
    flags = staleness.recompute_all(conn)
    assert any(f["sport_key"] == "cycling" for f in flags)
    # stored value is never changed
    row = conn.execute("SELECT value FROM sync_state WHERE key='thresholds.ftp'").fetchone()
    assert row["value"] == "250"


def test_no_flag_when_recent_within_margin(tmp_path):
    _, conn = _mk(tmp_path)
    conn.execute("INSERT INTO sync_state (key, value) VALUES ('thresholds.ftp', '250')")
    _ins_mmp(conn, 1, "2026-10-30T12:00:00+00:00", 1200, 252)
    conn.commit()
    flags = staleness.recompute_all(conn)
    assert flags == [] or not any(f["sport_key"] == "cycling" for f in flags)
