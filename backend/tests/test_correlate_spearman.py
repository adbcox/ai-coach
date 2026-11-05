"""Spearman + MWU correlation engine.

Uses synthetic daily series so we can assert directional sign + confidence.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from app import db
from app.coach_maths import correlate
from app.config import Settings


def _conn(tmp_path):
    s = Settings(data_dir=tmp_path, request_delay_s=0)
    db.init_db(s.db_path)
    return db.connect(s.db_path)


def _seed_monotonic(conn, days: int = 90, with_sick: bool = False):
    """Hot days → better readiness (positive correlation) with some noise.
    Sick days (if any) → much worse readiness."""
    start = date(2026, 7, 1)
    for i in range(days):
        day = (start + timedelta(days=i)).isoformat()
        apparent = 15.0 + (i % 20) * 1.0   # 15..35 °C
        precip = 0.0
        conn.execute(
            "INSERT INTO weather_day (day, temp_min_c, temp_max_c, apparent_mean_c, "
            "dew_point_mean_c, humidity_mean_pct, precip_mm, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, '2026-11-05T00:00:00+00:00')",
            (day, 10.0, apparent + 5, apparent, 8.0, 55.0, precip),
        )
        score = int(40 + (apparent - 15) * 2.5 + ((-1) ** i) * 2)
        if with_sick and i % 15 == 0:
            score = 20
            conn.execute(
                "INSERT INTO life_signal_day (day, travel, busy, sick, computed_at) "
                "VALUES (?, 0, 0, 1, '2026-11-05T00:00:00+00:00')",
                (day,),
            )
        else:
            if with_sick:
                conn.execute(
                    "INSERT INTO life_signal_day (day, travel, busy, sick, computed_at) "
                    "VALUES (?, 0, 0, 0, '2026-11-05T00:00:00+00:00')",
                    (day,),
                )
        conn.execute(
            "INSERT INTO readiness_day (day, score, band, hrv_part, sleep_part, rhr_part, "
            "load_part, checkin_part, inputs_json, computed_at) "
            "VALUES (?, ?, 'amber', NULL, NULL, NULL, NULL, NULL, '{}', '2026-11-05T00:00:00+00:00')",
            (day, max(0, min(100, score))),
        )
    conn.commit()


def test_positive_spearman_between_temp_and_readiness(tmp_path):
    conn = _conn(tmp_path)
    _seed_monotonic(conn, days=90)
    correlate.recompute_all(conn)
    rows = correlate.top_for(conn, y="readiness.score", min_abs_rho=0.2)
    hits = [r for r in rows if r["x"] == "weather.temp_c" and r["lag_days"] == 0]
    assert hits, f"expected a temp_c hit at lag 0; got {rows[:5]}"
    assert hits[0]["method"] == "spearman"
    assert hits[0]["rho"] > 0.5
    assert hits[0]["n"] >= 30
    assert hits[0]["ci_low"] < hits[0]["rho"] < hits[0]["ci_high"]


def test_mwu_fires_for_sick_vs_readiness(tmp_path):
    conn = _conn(tmp_path)
    _seed_monotonic(conn, days=90, with_sick=True)
    correlate.recompute_all(conn)
    rows = correlate.top_for(conn, y="readiness.score", min_abs_rho=0.1, limit=200)
    sick = [r for r in rows if r["x"] == "life.sick" and r["lag_days"] == 0]
    assert sick, f"expected a life.sick result; got {rows[:5]}"
    assert sick[0]["method"] == "mwu"
    # Sick days are much worse → effect size should be clearly negative.
    assert sick[0]["rho"] < -0.1


def test_insufficient_data_skips(tmp_path):
    conn = _conn(tmp_path)
    # Only 10 days of data → nothing reaches n >= 30.
    _seed_monotonic(conn, days=10)
    correlate.recompute_all(conn)
    assert conn.execute("SELECT COUNT(*) FROM correlations").fetchone()[0] == 0
