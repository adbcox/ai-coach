"""P3 — every tool returns the right shape on fixture data."""

from __future__ import annotations

from datetime import UTC, datetime


def _seed(conn):
    conn.execute(
        "INSERT INTO readiness_day (day, score, band, hrv_part, sleep_part, "
        "rhr_part, load_part, checkin_part, inputs_json, computed_at) VALUES "
        "('2026-11-05', 72, 'yellow', 10, 20, 15, 18, 9, '{\"note\":\"ok\"}', "
        "'2026-11-05T06:00:00+00:00')"
    )
    for d, tss in (("2026-11-03", 50), ("2026-11-04", 80), ("2026-11-05", 20)):
        conn.execute(
            "INSERT INTO training_load_day (day, trimp, tss, ctl, atl, tsb, acwr, computed_at) "
            "VALUES (?, ?, ?, 45, 60, -15, 1.1, '2026-11-05T06:00:00+00:00')",
            (d, tss, tss),
        )
    conn.execute(
        "INSERT INTO vdot_state (day, vdot, source, confidence) "
        "VALUES ('2026-11-05', 52.3, 'race', 0.9)"
    )
    conn.execute(
        "INSERT INTO activities (id, source, source_id, start_time, sport, name, "
        "distance_m, duration_s, created_at) VALUES "
        "(100, 'garmin', '100', '2026-11-04T12:00:00+00:00', 'cycling', 'ride', "
        "40000, 7200, '2026-11-04T14:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO ride_metrics (activity_id, family, np, if_, tss, ef, "
        "decoupling_pct, computed_at) VALUES "
        "(100, 'bike_road', 210, 0.85, 110.5, 1.55, 3.2, "
        "'2026-11-05T06:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO mean_max_power (activity_id, window_s, watts) VALUES (100, 60, 350)"
    )
    conn.execute(
        "INSERT INTO mean_max_power (activity_id, window_s, watts) VALUES (100, 300, 280)"
    )
    conn.execute(
        "INSERT INTO activity_weather (activity_id, feels_like_c, temp_c, dew_point_c, "
        "humidity_pct, wind_m_s, precip_mm, source, fetched_at) VALUES "
        "(100, 24, 22, 10, 55, 3.5, 0, 'test', '2026-11-05T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO ride_disagreement (activity_id, disagreement_score, cause, "
        "confidence, evidence_json, computed_at) VALUES "
        "(100, 0.4, 'fatigue', 0.7, '{\"zone_shift\":0.6}', '2026-11-05T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO thresholds_staleness (sport_key, stored, suggested, "
        "evidence_json, computed_at) VALUES "
        "('bike_ftp', 260, 268, '{\"best_20min_w\":282}', '2026-11-05T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO ha_daily (day, bedroom_temp_c_night, bedroom_rh_pct_night, "
        "bed_in_time, bed_out_time, computed_at) VALUES "
        "('2026-11-05', 19.5, 45, '23:15', '06:45', '2026-11-05T07:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO correlations (y, x, lag_days, n, rho, ci_low, ci_high, method, "
        "p_approx, computed_at) VALUES ('readiness.score', 'weather.temp_c', 0, 80, "
        "0.3, 0.1, 0.5, 'spearman', 0.01, '2026-11-05T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO checkins (day, overall, legs, sleep_feel, stress, alcohol_units, "
        "ill, note, created_at) VALUES "
        "('2026-11-05', 4, 4, 4, 2, 0, 0, 'fine', '2026-11-05T06:00:00+00:00')"
    )
    conn.commit()


def test_tools_shapes(authed, settings):
    from app import db
    from app.coach import tools

    conn = db.connect(settings.db_path)
    try:
        _seed(conn)

        r = tools.get_readiness(conn, day="2026-11-05")
        assert r["score"] == 72 and r["band"] == "yellow"
        assert r["inputs"] == {"note": "ok"}

        r = tools.get_training_load(conn, days=3)
        assert len(r["days"]) == 3
        assert r["days"][-1]["day"] == "2026-11-05"

        r = tools.get_predictions(conn)
        assert r["vdot"]["vdot"] == 52.3

        r = tools.get_activity_metrics(conn, activity_id=100)
        assert r["np"] == 210 and r["tss"] == 110.5

        r = tools.get_best_efforts(conn, sport="cycling", window_days=365)
        bests = {b["window_s"]: b["watts"] for b in r["power_bests"]}
        assert bests[60] == 350 and bests[300] == 280

        r = tools.get_weather_for_activity(conn, activity_id=100)
        assert r["feels_like_c"] == 24

        r = tools.get_disagreement(conn, activity_id=100)
        assert r["cause"] == "fatigue"
        assert r["evidence"] == {"zone_shift": 0.6}

        r = tools.get_thresholds_staleness(conn)
        assert r["stale"][0]["sport_key"] == "bike_ftp"
        assert r["stale"][0]["evidence"] == {"best_20min_w": 282}

        r = tools.get_hass_daily(conn, day="2026-11-05")
        assert r["ha_daily"]["bedroom_temp_c_night"] == 19.5

        r = tools.get_correlations(conn, y="readiness.score", min_abs_rho=0.2, min_n=10)
        assert r["note"] == "association, not cause"
        assert any(row["x"] == "weather.temp_c" for row in r["rows"])

        r = tools.get_checkin_prompt(conn)
        assert r["prompt"].startswith("How do you feel")

        r = tools.get_suggested_workout(conn, day="2026-11-05")
        assert "primary" in r

        r = tools.get_routine_profile(conn)
        assert "routine" in r
    finally:
        conn.close()


def test_call_tool_errors(authed, settings):
    from app import db
    from app.coach import tools

    conn = db.connect(settings.db_path)
    try:
        assert tools.call_tool(conn, "nope", {})["error"].startswith("unknown tool")
        bad = tools.call_tool(conn, "get_readiness", {"missing_kw": 1})
        assert "bad arguments" in bad["error"]
    finally:
        conn.close()
