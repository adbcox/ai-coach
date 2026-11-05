"""Nightly routine profile builder."""

from __future__ import annotations

import json
from datetime import date, timedelta

from app import db
from app.coach_maths import routine
from app.config import Settings


def _conn(tmp_path):
    s = Settings(data_dir=tmp_path, request_delay_s=0)
    db.init_db(s.db_path)
    return db.connect(s.db_path)


def _seed_activity(conn, aid, iso_day, family="bike_road", duration_s=3600,
                   tss=80, decoupling_pct=4.5, ef=1.7, intervals=False):
    conn.execute(
        "INSERT INTO activities (id, source, source_id, start_time, sport, name, "
        "distance_m, duration_s, created_at) VALUES "
        "(?, 'garmin', ?, ?, 'cycling', 'x', 20000, ?, '2026-11-05T00:00:00+00:00')",
        (aid, str(aid), f"{iso_day}T12:00:00+00:00", duration_s),
    )
    conn.execute(
        "INSERT INTO activity_load (activity_id, family, tss, method, computed_at) "
        "VALUES (?, ?, ?, 'test', '2026-11-05T00:00:00+00:00')",
        (aid, family, tss),
    )
    conn.execute(
        "INSERT INTO ride_metrics (activity_id, family, decoupling_pct, ef, computed_at) "
        "VALUES (?, ?, ?, ?, '2026-11-05T00:00:00+00:00')",
        (aid, family, decoupling_pct, ef),
    )
    if intervals:
        conn.execute(
            "INSERT INTO detected_intervals (activity_id, idx, start_offset_s, "
            "end_offset_s, work_or_rest) VALUES (?, 0, 0, 600, 'work')",
            (aid,),
        )


def test_weekday_and_season_populated(tmp_path):
    conn = _conn(tmp_path)
    # Three months of regular Tuesday and Saturday rides.
    start = date(2026, 7, 1)
    aid = 1
    for i in range(90):
        d = start + timedelta(days=i)
        if d.weekday() == 1:  # Tuesday interval
            _seed_activity(conn, aid, d.isoformat(), tss=95, duration_s=3000,
                           intervals=True)
            aid += 1
        if d.weekday() == 5:  # Saturday long
            _seed_activity(conn, aid, d.isoformat(), tss=180, duration_s=10800,
                           decoupling_pct=6.0, ef=1.85)
            aid += 1
    conn.commit()
    routine.recompute_profile(conn, today=date(2026, 10, 1))
    latest = routine.latest(conn)
    assert latest is not None
    prof = latest["profile"]
    # Tuesday bike_road should be "usual" (>=30 % of Tuesdays).
    tue = prof["by_weekday_family"]["90d"].get("1:bike_road")
    assert tue is not None
    assert tue["usual"] is True
    # Saturday long session captured.
    sat = prof["by_weekday_family"]["90d"].get("5:bike_road")
    assert sat["duration_min"]["p50"] >= 150
    # Summer (JJA) season stats.
    assert "JJA:bike_road" in prof["by_season_family"]


def test_recurring_sessions_cluster_names(tmp_path):
    conn = _conn(tmp_path)
    start = date(2026, 1, 1)
    aid = 1
    # 40 short recovery rides.
    for i in range(40):
        _seed_activity(conn, aid, (start + timedelta(days=i)).isoformat(),
                       duration_s=1800, tss=25, decoupling_pct=1.0, ef=1.6)
        aid += 1
    # 40 long endurance.
    for i in range(40):
        _seed_activity(conn, aid, (start + timedelta(days=100 + i)).isoformat(),
                       duration_s=11000, tss=180, decoupling_pct=5.0, ef=1.85)
        aid += 1
    conn.commit()
    routine.recompute_profile(conn, today=date(2026, 7, 1))
    prof = routine.latest(conn)["profile"]
    bike_clusters = prof["recurring_sessions"].get("bike_road") or []
    names = {c["cluster"] for c in bike_clusters}
    assert "short recovery" in names
    assert any(n in names for n in ("endurance long", "endurance medium"))


def test_long_session_day_is_saturday(tmp_path):
    conn = _conn(tmp_path)
    start = date(2026, 1, 1)
    aid = 1
    for i in range(60):
        d = start + timedelta(days=i)
        if d.weekday() == 5:
            _seed_activity(conn, aid, d.isoformat(), duration_s=11000, tss=180)
        else:
            _seed_activity(conn, aid, d.isoformat(), duration_s=3600, tss=60)
        aid += 1
    conn.commit()
    routine.recompute_profile(conn, today=date(2026, 3, 15))
    prof = routine.latest(conn)["profile"]
    assert prof["long_session_day"]["weekday"] == 5
