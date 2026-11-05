"""Hard-gate readiness overrides."""

from __future__ import annotations

from datetime import date, timedelta

from app import db
from app.coach_maths import routine, suggest
from app.config import Settings


def _conn(tmp_path):
    s = Settings(data_dir=tmp_path, request_delay_s=0)
    db.init_db(s.db_path)
    return db.connect(s.db_path)


def _seed(conn, aid, iso_day, tss=90, duration_s=3000, intervals=True):
    conn.execute(
        "INSERT INTO activities (id, source, source_id, start_time, sport, name, "
        "distance_m, duration_s, created_at) VALUES "
        "(?, 'garmin', ?, ?, 'cycling', 'x', 20000, ?, '2026-11-05T00:00:00+00:00')",
        (aid, str(aid), f"{iso_day}T12:00:00+00:00", duration_s),
    )
    conn.execute(
        "INSERT INTO activity_load (activity_id, family, tss, method, computed_at) "
        "VALUES (?, 'bike_road', ?, 'test', '2026-11-05T00:00:00+00:00')",
        (aid, tss),
    )
    conn.execute(
        "INSERT INTO ride_metrics (activity_id, family, decoupling_pct, ef, computed_at) "
        "VALUES (?, 'bike_road', 4.0, 1.75, '2026-11-05T00:00:00+00:00')",
        (aid,),
    )
    if intervals:
        conn.execute(
            "INSERT INTO detected_intervals (activity_id, idx, start_offset_s, "
            "end_offset_s, work_or_rest) VALUES (?, 0, 0, 600, 'work')",
            (aid,),
        )


def _build_history(conn, today):
    """120 days of Tue intervals + Thu recoveries so profile has both."""
    aid = 1
    for i in range(120):
        d = today - timedelta(days=120 - i)
        if d.weekday() == 1:
            _seed(conn, aid, d.isoformat(), tss=90, duration_s=3000, intervals=True)
            aid += 1
        if d.weekday() == 3:
            _seed(conn, aid, d.isoformat(), tss=25, duration_s=1800, intervals=False)
            aid += 1
    conn.commit()
    routine.recompute_profile(conn, today=today)


def test_ill_forces_recovery_first(tmp_path):
    conn = _conn(tmp_path)
    today = date(2026, 10, 6)
    _build_history(conn, today)
    conn.execute(
        "INSERT INTO checkins (day, overall, legs, sleep_feel, stress, "
        "alcohol_units, ill, note, created_at) VALUES "
        "(?, 3, 3, 3, 3, 0, 1, NULL, '2026-11-05T00:00:00+00:00')",
        (today.isoformat(),),
    )
    conn.commit()
    res = suggest.suggest_today(conn, today=today)
    assert res["primary"]["cluster"] == "short recovery"


def test_red_band_drops_hard(tmp_path):
    conn = _conn(tmp_path)
    today = date(2026, 10, 6)
    _build_history(conn, today)
    conn.execute(
        "INSERT INTO readiness_day (day, score, band, inputs_json, computed_at) "
        "VALUES (?, 20, 'red', '{}', '2026-11-05T00:00:00+00:00')",
        (today.isoformat(),),
    )
    conn.commit()
    res = suggest.suggest_today(conn, today=today)
    assert res["primary"] is not None
    for cand in res["candidates"]:
        assert cand["cluster"] not in {"tempo medium", "interval hard",
                                       "VO2 hard", "race"}


def test_tsb_minus_25_downgrades_hard(tmp_path):
    conn = _conn(tmp_path)
    today = date(2026, 10, 6)
    _build_history(conn, today)
    conn.execute(
        "INSERT INTO training_load_day (day, trimp, tss, ctl, atl, tsb, "
        "computed_at) VALUES (?, 0, 0, 55, 80, -25, '2026-11-05T00:00:00+00:00')",
        ((today - timedelta(days=1)).isoformat(),),
    )
    conn.commit()
    res = suggest.suggest_today(conn, today=today)
    hard = [c for c in res["candidates"]
            if c["cluster"] in {"tempo medium", "interval hard", "VO2 hard"}]
    # All hard candidates should be downgraded (note recorded).
    for cand in hard:
        assert any("downgraded" in n for n in cand["notes"])
