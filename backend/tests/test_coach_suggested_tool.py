"""P3 — /api/coach/daily forces get_suggested_workout, reply quotes it.

The LLM is mocked. We seed a `routine_profile` row rich enough that
`suggest_today` returns a non-null primary, then assert the mocked daily
reply quotes a value verbatim from the tool payload.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx

from app.coach import client as coach_client


def _scripted_transport(script):
    turns = iter(script)

    def handler(request: httpx.Request) -> httpx.Response:
        try:
            step = next(turns)
        except StopIteration:
            return httpx.Response(500, json={"error": "exhausted"})
        msg = {"role": "assistant",
               "content": step.get("content"),
               "tool_calls": step.get("tool_calls")}
        return httpx.Response(200, json={
            "choices": [{"message": msg,
                         "finish_reason": "stop" if step.get("content") else "tool_calls"}],
        })

    return httpx.MockTransport(handler)


def _patch_client(monkeypatch, script):
    transport = _scripted_transport(script)
    original_client = httpx.Client

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(coach_client.httpx, "Client", fake_client)


def _seed(conn, today):
    weekday = today.weekday()
    # One cluster, fully concentrated on today's weekday.
    weekday_dist = [0.0] * 7
    weekday_dist[weekday] = 1.0
    profile = {
        "by_weekday_family": {
            "90d": {
                f"{weekday}:bike_road": {
                    "duration_min": {"n": 48, "p50": 60.0, "p90": 90.0},
                    "freq_on_weekday": 0.9,
                }
            },
            "365d": {}, "all": {},
        },
        "by_season_family": {},
        "weekly_rhythm": {"patterns": [{"pattern": ["E"] * 7, "count": 1}]},
        "recurring_sessions": {
            "bike_road": [
                {"cluster": "endurance medium",
                 "centroid": {"duration_min": 60.0, "tss": 55.0,
                              "decoupling_pct": 4.0, "has_intervals": 0.0},
                 "weekday_dist": weekday_dist}
            ]
        },
        "long_session_day": {},
        "prelude_signatures": {},
    }
    conn.execute(
        "INSERT INTO routine_profile (computed_at, profile_json) VALUES (?, ?)",
        (datetime.now(UTC).isoformat(timespec="seconds"), json.dumps(profile)),
    )
    for d, tss in ((today - timedelta(days=2), 40),
                    (today - timedelta(days=1), 60),
                    (today, 0)):
        conn.execute(
            "INSERT INTO training_load_day (day, trimp, tss, ctl, atl, tsb, acwr, computed_at) "
            "VALUES (?, ?, ?, 45, 50, -5, 1.0, '2026-11-05T06:00:00+00:00')",
            (d.isoformat(), tss, tss),
        )
    conn.execute(
        "INSERT INTO readiness_day (day, score, band, hrv_part, sleep_part, "
        "rhr_part, load_part, checkin_part, inputs_json, computed_at) VALUES "
        "(?, 70, 'yellow', 10, 20, 15, 18, 9, '{}', ?)",
        (today.isoformat(), datetime.now(UTC).isoformat(timespec="seconds")),
    )
    conn.commit()


def test_daily_forces_suggest_and_quotes_tool_payload(monkeypatch, authed, settings):
    from app import db
    from app.coach_maths import suggest as _sg

    conn = db.connect(settings.db_path)
    try:
        today = datetime.now(UTC).date()
        _seed(conn, today)
        payload = _sg.suggest_today(conn, today=today)
    finally:
        conn.close()

    primary = payload["primary"]
    assert primary is not None, "test seed failed to produce a primary suggestion"
    cluster = primary["cluster"]
    duration = primary["duration_min"]

    script = [
        {"tool_calls": [{
            "id": "c1", "type": "function",
            "function": {"name": "get_suggested_workout",
                         "arguments": json.dumps({"day": today.isoformat()})},
        }]},
        {"content": (
            f"Primary: {cluster} ({duration} min). "
            f"Readiness normal; form -5."
        )},
    ]
    _patch_client(monkeypatch, script)

    r = authed.post("/api/coach/daily")
    assert r.status_code == 200, r.text
    body = r.json()
    tools = [t["tool"] for t in body["tools_used"]]
    assert tools[0] == "get_suggested_workout"
    # reply quotes the cluster name verbatim from the tool output
    assert cluster in body["reply"]


def test_ride_endpoint_404_for_unknown_activity(authed):
    r = authed.post("/api/coach/ride/999999")
    assert r.status_code == 404
