"""Suggestion feedback + actual-activity matching."""

from __future__ import annotations

import json
from datetime import date

from app import db
from app.coach_maths import suggest
from app.config import Settings


def _conn(tmp_path):
    s = Settings(data_dir=tmp_path, request_delay_s=0)
    db.init_db(s.db_path)
    return db.connect(s.db_path)


def _insert_activity(conn, aid, iso_day, duration_s, tss):
    conn.execute(
        "INSERT INTO activities (id, source, source_id, start_time, sport, name, "
        "distance_m, duration_s, created_at) VALUES "
        "(?, 'garmin', ?, ?, 'cycling', 'x', 20000, ?, '2026-11-05T00:00:00+00:00')",
        (aid, str(aid), f"{iso_day}T09:00:00+00:00", duration_s),
    )
    conn.execute(
        "INSERT INTO activity_load (activity_id, family, tss, method, computed_at) "
        "VALUES (?, 'bike_road', ?, 'test', '2026-11-05T00:00:00+00:00')",
        (aid, tss),
    )


def test_write_and_record_feedback(tmp_path):
    conn = _conn(tmp_path)
    today = date(2026, 10, 6)
    suggestion = {
        "day": today.isoformat(),
        "generated_at": "2026-10-06T06:00:00+00:00",
        "primary": {"family": "bike_road", "cluster": "tempo medium",
                    "duration_min": 55.0, "tss": 85.0},
        "alternative": {"family": "bike_road", "cluster": "endurance medium",
                        "duration_min": 70.0, "tss": 70.0},
    }
    sid = suggest.write_suggestion(conn, suggestion)
    suggest.record_feedback(conn, sid, "did_it")
    row = conn.execute(
        "SELECT user_action, recorded_at FROM suggestion_history WHERE id = ?",
        (sid,),
    ).fetchone()
    assert row["user_action"] == "did_it"
    assert row["recorded_at"] is not None


def test_invalid_user_action_rejected(tmp_path):
    conn = _conn(tmp_path)
    sid = suggest.write_suggestion(conn, {
        "day": "2026-10-06", "generated_at": "2026-10-06T06:00:00+00:00",
        "primary": {"family": "bike_road", "cluster": "tempo medium",
                    "duration_min": 55.0, "tss": 85.0},
        "alternative": None,
    })
    try:
        suggest.record_feedback(conn, sid, "nope")
    except ValueError:
        return
    raise AssertionError("expected ValueError for unknown user_action")


def test_match_actual_picks_closest(tmp_path):
    conn = _conn(tmp_path)
    today = date(2026, 10, 6)
    # Suggestion asks for ~55 min / 85 TSS.
    sid = suggest.write_suggestion(conn, {
        "day": today.isoformat(),
        "generated_at": "2026-10-06T06:00:00+00:00",
        "primary": {"family": "bike_road", "cluster": "tempo medium",
                    "duration_min": 55.0, "tss": 85.0},
        "alternative": None,
    })
    # Three candidate rides done today.
    _insert_activity(conn, 101, today.isoformat(), 3300, 83)   # 55 min / 83 — closest
    _insert_activity(conn, 102, today.isoformat(), 1800, 30)   # 30 min / 30
    _insert_activity(conn, 103, today.isoformat(), 10800, 180) # 3h / 180
    conn.commit()
    n = suggest.match_actual(conn, today)
    assert n == 1
    row = conn.execute(
        "SELECT actual_activity_id, actual_similarity FROM suggestion_history "
        "WHERE id = ?", (sid,),
    ).fetchone()
    assert row["actual_activity_id"] == 101
    assert row["actual_similarity"] > 0.9
