"""Composite ranker sanity tests."""

from __future__ import annotations

import json
from datetime import date, timedelta

from app import db
from app.coach_maths import routine, suggest
from app.config import Settings


def _conn(tmp_path):
    s = Settings(data_dir=tmp_path, request_delay_s=0)
    db.init_db(s.db_path)
    return db.connect(s.db_path)


def _seed(conn, aid, iso_day, family="bike_road", duration_s=5400,
          tss=90, dec=4.0, ef=1.75, intervals=False):
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
        (aid, family, dec, ef),
    )
    if intervals:
        conn.execute(
            "INSERT INTO detected_intervals (activity_id, idx, start_offset_s, "
            "end_offset_s, work_or_rest) VALUES (?, 0, 0, 600, 'work')",
            (aid,),
        )


def test_tuesday_prefers_usual_interval_session(tmp_path):
    conn = _conn(tmp_path)
    today = date(2026, 10, 6)  # Tuesday
    start = today - timedelta(days=120)
    aid = 1
    # Tuesdays: tempo intervals, 50-min 90-TSS.
    # Thursdays: short recovery, 30-min 25-TSS.
    for i in range(120):
        d = start + timedelta(days=i)
        if d.weekday() == 1:
            _seed(conn, aid, d.isoformat(), tss=90, duration_s=3000, intervals=True)
            aid += 1
        if d.weekday() == 3:
            _seed(conn, aid, d.isoformat(), tss=25, duration_s=1800, dec=1.5)
            aid += 1
    conn.commit()
    routine.recompute_profile(conn, today=today)
    res = suggest.suggest_today(conn, today=today)
    assert res["primary"] is not None
    # On a Tuesday, intervals/tempo should beat short recovery.
    assert res["primary"]["cluster"] in {"tempo medium", "interval hard"}
    assert res["primary"]["family"] == "bike_road"


def test_low_confidence_flag_when_few_samples(tmp_path):
    conn = _conn(tmp_path)
    today = date(2026, 10, 6)
    # Only 6 rides on Tuesdays → n_history < 20.
    aid = 1
    for i in range(6):
        d = today - timedelta(days=7 * (i + 1))
        _seed(conn, aid, d.isoformat(), tss=90, duration_s=3000)
        aid += 1
    conn.commit()
    routine.recompute_profile(conn, today=today)
    res = suggest.suggest_today(conn, today=today)
    assert res["primary"] is not None
    assert res["low_confidence"] is True
