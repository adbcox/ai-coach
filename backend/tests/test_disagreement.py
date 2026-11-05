"""Power-vs-HR disagreement detector."""

from __future__ import annotations

import json

from app import db
from app.coach_maths import pwr_hr_disagreement as det
from app.config import Settings


def _conn(tmp_path):
    s = Settings(data_dir=tmp_path, request_delay_s=0)
    db.init_db(s.db_path)
    return db.connect(s.db_path)


def _seed_ride(conn, aid: int, hrs: list[float], pwrs: list[float],
               ftp: float = 250, lthr: float = 160,
               feels_like_c: float = 15.0, tsb: float | None = None,
               pacing_cv: float = 0.2, sport: str = "cycling",
               start: str = "2026-10-10T12:00:00+00:00"):
    conn.execute("INSERT OR REPLACE INTO sync_state (key, value) VALUES ('thresholds.ftp', ?)",
                 (str(ftp),))
    conn.execute("INSERT OR REPLACE INTO sync_state (key, value) VALUES ('thresholds.lthr', ?)",
                 (str(lthr),))
    conn.execute(
        "INSERT INTO activities (id, source, source_id, start_time, sport, name, "
        "distance_m, duration_s, created_at) "
        "VALUES (?, 'garmin', ?, ?, ?, 'x', 10000, 3600, '2026-11-05T00:00:00+00:00')",
        (aid, str(aid), start, sport),
    )
    conn.execute(
        "INSERT INTO ride_metrics (activity_id, family, np, pacing_cv, computed_at) "
        "VALUES (?, 'bike_road', 200, ?, '2026-11-05T00:00:00+00:00')",
        (aid, pacing_cv),
    )
    conn.execute(
        "INSERT INTO activity_weather (activity_id, feels_like_c, source, fetched_at) "
        "VALUES (?, ?, 'test', '2026-11-05T00:00:00+00:00')",
        (aid, feels_like_c),
    )
    if tsb is not None:
        conn.execute(
            "INSERT OR REPLACE INTO training_load_day (day, trimp, tss, ctl, atl, tsb, "
            "computed_at) VALUES (date(?), 0, 0, 50, 50, ?, '2026-11-05T00:00:00+00:00')",
            (start, tsb),
        )
    t = 0
    for hr, pw in zip(hrs, pwrs, strict=False):
        conn.execute("INSERT INTO samples (activity_id, t, hr, power) VALUES (?, ?, ?, ?)",
                     (aid, t, int(hr), int(pw)))
        t += 1
    conn.commit()


def test_heat_cause_fires(tmp_path):
    conn = _conn(tmp_path)
    # Power in Z2 (~200W under FTP=250), HR cardiac-drift into Z4 (~160 bpm).
    # Large zone shift + high fraction disagreeing + hot day.
    _seed_ride(conn, 1, hrs=[160] * 120, pwrs=[180] * 120, feels_like_c=28.0)
    det.recompute_all(conn)
    row = conn.execute(
        "SELECT cause, disagreement_score FROM ride_disagreement WHERE activity_id = 1"
    ).fetchone()
    assert row["cause"] == "heat"
    assert row["disagreement_score"] > 0.6


def test_low_score_returns_null_cause(tmp_path):
    conn = _conn(tmp_path)
    # Both in Z2 → median zones match, zero disagreement.
    # HR 135/160 = 0.84 (boundary 0.88 → Z2);  power 215/250 = 0.86 (boundary 0.90 → Z2).
    _seed_ride(conn, 1, hrs=[135] * 120, pwrs=[215] * 120, feels_like_c=15.0)
    det.recompute_all(conn)
    row = conn.execute(
        "SELECT cause, disagreement_score FROM ride_disagreement WHERE activity_id = 1"
    ).fetchone()
    assert row["cause"] is None
    assert row["disagreement_score"] < 0.6


def test_fatigue_cause_beats_terrain(tmp_path):
    conn = _conn(tmp_path)
    _seed_ride(conn, 1, hrs=[160] * 120, pwrs=[180] * 120, feels_like_c=12.0,
               tsb=-20.0, pacing_cv=0.5)
    det.recompute_all(conn)
    row = conn.execute(
        "SELECT cause FROM ride_disagreement WHERE activity_id = 1"
    ).fetchone()
    assert row["cause"] == "fatigue"


def test_missing_thresholds_skips_activity(tmp_path):
    conn = _conn(tmp_path)
    # Seed samples WITHOUT setting FTP/LTHR.
    conn.execute(
        "INSERT INTO activities (id, source, source_id, start_time, sport, name, "
        "distance_m, duration_s, created_at) "
        "VALUES (1, 'garmin', '1', '2026-10-10T12:00:00+00:00', 'cycling', 'x', "
        "        10000, 3600, '2026-11-05T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO ride_metrics (activity_id, family, np, pacing_cv, computed_at) "
        "VALUES (1, 'bike_road', 200, 0.2, '2026-11-05T00:00:00+00:00')"
    )
    for t in range(120):
        conn.execute("INSERT INTO samples (activity_id, t, hr, power) VALUES (1, ?, 150, 180)", (t,))
    conn.commit()
    det.recompute_all(conn)
    row = conn.execute("SELECT COUNT(*) FROM ride_disagreement").fetchone()
    assert row[0] == 0
