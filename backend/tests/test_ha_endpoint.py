"""P5: /api/ha/today — deterministic HA tile. No LLM call."""

from __future__ import annotations

from datetime import date


def test_ha_today_shape_on_empty_day(authed):
    """Shape is stable even when no data exists — nulls allowed everywhere
    except suggestion.one_line, which must be non-empty if readiness.score is."""
    r = authed.get("/api/ha/today")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == {"readiness", "suggestion", "tsb", "generated_at"}
    assert "score" in body["readiness"] and "band" in body["readiness"]
    assert body["readiness"]["score"] is None
    assert body["readiness"]["band"] is None
    assert body["suggestion"] is None
    assert body["tsb"] is None
    assert isinstance(body["generated_at"], str)
    assert body["generated_at"].endswith("+00:00")


def test_ha_today_populated(authed, settings, monkeypatch):
    """When readiness + load + a suggest primary all exist, HA tile composes
    a non-empty one_line and surfaces readiness band + tsb."""
    from app import db
    today = date.today().isoformat()
    conn = db.connect(settings.db_path)
    try:
        conn.execute(
            "INSERT INTO readiness_day (day, score, band, inputs_json, computed_at) "
            "VALUES (?, 72, 'green', '{}', '2026-11-05T06:00:00+00:00')",
            (today,),
        )
        conn.execute(
            "INSERT INTO training_load_day (day, trimp, tss, ctl, atl, tsb, acwr, "
            "computed_at) VALUES (?, 60, 80, 55.2, 49.8, 5.4, 1.1, "
            "'2026-11-05T06:00:00+00:00')",
            (today,),
        )
        conn.commit()
    finally:
        conn.close()

    # suggest.suggest_today requires a full routine_profile pipeline — mock it
    # so this test stays focused on the HA composition logic.
    from app.coach_maths import suggest as _sug
    monkeypatch.setattr(_sug, "suggest_today", lambda c, **_: {
        "day": today, "generated_at": "2026-11-05T06:30:00+00:00",
        "primary": {
            "family": "bike_road", "cluster": "endurance", "duration_min": 75,
            "tss": 85, "decoupling_pct": 2.0, "has_intervals": False, "score": 0.72,
            "components": {"w1_weekday": 0.6, "w2_season": 0.3, "w3_prelude": 0.3, "w4_rhythm": 0.4},
            "n_history": 24, "notes": [],
        },
        "alternative": None, "candidates": [],
        "low_confidence": False, "context": {},
    })

    r = authed.get("/api/ha/today")
    assert r.status_code == 200
    body = r.json()
    assert body["readiness"]["score"] == 72
    assert body["readiness"]["band"] == "green"
    assert body["tsb"] == 5.4
    s = body["suggestion"]
    assert s is not None
    assert s["sport"] == "bike_road"
    assert s["duration_min"] == 75
    assert s["intensity"] == "zone 2"
    assert isinstance(s["one_line"], str) and len(s["one_line"]) > 0
    assert "75 min" in s["one_line"]
    assert s["low_confidence"] is False
