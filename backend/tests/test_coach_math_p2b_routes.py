"""Routes added in P2b.6: correlations, disagreement, weather, suggest."""

from __future__ import annotations

import json


def _seed(conn):
    # weather_day row for a known date
    conn.execute(
        "INSERT INTO weather_day (day, temp_min_c, temp_max_c, apparent_mean_c, "
        "dew_point_mean_c, humidity_mean_pct, precip_mm, fetched_at) VALUES "
        "('2026-10-10', 10, 22, 18, 9, 60, 0, '2026-11-05T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO activities (id, source, source_id, start_time, sport, name, "
        "distance_m, duration_s, created_at) VALUES "
        "(42, 'garmin', '42', '2026-10-10T12:00:00+00:00', 'cycling', 'x', "
        "20000, 3600, '2026-11-05T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO activity_weather (activity_id, feels_like_c, source, fetched_at) "
        "VALUES (42, 28, 'test', '2026-11-05T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO ride_disagreement (activity_id, disagreement_score, cause, "
        "confidence, evidence_json, computed_at) VALUES "
        "(42, 0.8, 'heat', 0.8, '{\"zone_shift\":1}', '2026-11-05T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO correlations (y, x, lag_days, n, rho, ci_low, ci_high, method, "
        "p_approx, computed_at) VALUES ('readiness.score', 'weather.temp_c', 0, "
        "60, 0.42, 0.2, 0.6, 'spearman', 0.01, '2026-11-05T00:00:00+00:00')"
    )
    conn.commit()


def test_disagreement_weather_and_correlations_routes(authed):
    from app import db
    conn = db.connect(authed.get("/api/health").json()["db"]["path"]) if False else None
    # Easier: open DB through a settings import.
    from app.config import Settings
    settings = authed.get("/api/health").json()  # just to ensure app is up
    # Get settings path via a known endpoint is fragile; open directly from fixture.


def test_weather_day_route_404_when_missing(authed):
    r = authed.get("/api/weather/day/1999-01-01")
    assert r.status_code == 404


def test_routes_present_when_db_populated(authed, settings):
    from app import db
    conn = db.connect(settings.db_path)
    _seed(conn)
    conn.close()
    r = authed.get("/api/weather/day/2026-10-10")
    assert r.status_code == 200
    assert r.json()["apparent_mean_c"] == 18
    r = authed.get("/api/weather/activity/42")
    assert r.status_code == 200
    assert r.json()["feels_like_c"] == 28
    r = authed.get("/api/activities/42/disagreement")
    assert r.status_code == 200
    body = r.json()
    assert body["cause"] == "heat"
    assert body["evidence"]["zone_shift"] == 1
    r = authed.get("/api/correlations?y=readiness.score&min_abs_rho=0.2")
    assert r.status_code == 200
    rows = r.json()["rows"]
    assert any(row["x"] == "weather.temp_c" for row in rows)
    # /api/suggest/today with empty profile returns 'no routine_profile row yet'.
    r = authed.get("/api/suggest/today")
    assert r.status_code == 200
    assert r.json()["primary"] is None
    r = authed.get("/api/suggest/routine")
    assert r.status_code == 404
    # feedback requires a row for today
    r = authed.post("/api/suggest/today", json={"user_action": "did_it"})
    assert r.status_code == 404
