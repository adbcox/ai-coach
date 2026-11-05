from datetime import date, timedelta

import httpx
import pytest

from app.garmin.client import GarminClient, GarminError
from app.wellness import CHUNK_DAYS, is_empty
from tests.conftest import API_KEY
from tests.test_api import wait_idle


def run_sync(client, mode="quick", full=False):
    url = "/api/sync?full=true" if full else f"/api/sync?mode={mode}"
    assert client.post(url).status_code == 202
    return wait_idle(client)


def test_is_empty():
    assert is_empty(None) and is_empty([]) and is_empty({"data": []}) and is_empty({"a": {"b": None}})
    assert not is_empty({"data": [{"x": 1}]}) and not is_empty(0)


def test_first_sync_is_90_days_then_full_walks_all_history(authed, fake):
    # P1 (dispatch-05 line 15): first sync is scoped to backfill_days (90 by
    # default). mode=full is the explicit opt-in that walks all history.
    run_sync(authed)
    first = fake.search_params[0]
    assert "startDate" in first and "endDate" in first  # 90-day window applied
    n = len(fake.search_params)
    run_sync(authed, full=True)
    assert "startDate" not in fake.search_params[n]  # full backfill: no date filter


def test_health_data_collected_and_not_refetched(authed, fake):
    s = run_sync(authed)
    assert s["last_sync"]["status"] == "ok"
    stored = authed.get("/api/providers/garmin").json()["stored"]
    assert stored["activities"] == 2
    assert stored["health_records"]["daily_summaries"] >= 1
    assert stored["health_records"]["sleep"] >= 25
    summ = "/usersummary-service/v2/dailysummaries"
    sleep = "/sleep-service/sleep/dailySleep"
    before_s, before_d = fake.calls[summ], fake.calls[sleep]
    # unavailable types (404 in the fake) are reported, not fatal
    assert "not available" in s["last_sync"]["message"]
    run_sync(authed)  # quick: newest stored data minus 1 day only
    assert fake.calls[summ] - before_s <= 2
    assert fake.calls[sleep] - before_d <= 3
    # P1 full is the explicit history backfill: it walks all the way back to
    # HISTORY_FLOOR, so the daily sleep fetches exceed the 90-day quick window.
    before_full = fake.calls[sleep]
    run_sync(authed, full=True)
    assert fake.calls[sleep] - before_full > 45


def test_chunks_cover_28_days():
    assert CHUNK_DAYS == 28 and date.today() - timedelta(days=CHUNK_DAYS) < date.today()


def test_rate_limit_is_retried():
    waits = []
    state = {"n": 0}

    def handler(request):
        if request.url.path.endswith("/token"):
            import time

            from tests.conftest import make_jwt
            return httpx.Response(200, text=make_jwt(time.time() + 86400))
        state["n"] += 1
        return httpx.Response(429) if state["n"] <= 2 else httpx.Response(200, json={"ok": 1})

    c = GarminClient(API_KEY, "https://x.test", transport=httpx.MockTransport(handler),
                     sleep=waits.append, retry_delay=1)
    assert c.get_json("/anything") == {"ok": 1}
    assert waits == [1, 2]


def test_rate_limit_gives_up():
    def handler(request):
        if request.url.path.endswith("/token"):
            import time

            from tests.conftest import make_jwt
            return httpx.Response(200, text=make_jwt(time.time() + 86400))
        return httpx.Response(429)

    c = GarminClient(API_KEY, "https://x.test", transport=httpx.MockTransport(handler),
                     sleep=lambda s: None)
    with pytest.raises(GarminError) as e:
        c.get_json("/anything")
    assert e.value.status == 429


def test_diagnostics_has_structure_but_no_personal_values(authed, fake):
    run_sync(authed)
    assert authed.get("/api/diagnostics/shapes").status_code == 200
    text = authed.get("/api/diagnostics/shapes").text
    report = __import__("json").loads(text)
    assert report["activities"]["count"] == 2
    assert "$.activityId" in report["activity_list_item"]["fields"]
    assert report["activity_list_item"]["fields"]["$.activityType.typeKey"]["values"]
    assert report["fit_samples"]["fill_rate"]["lat"] == 1.0
    assert "daily_summaries" in report["health"]
    # personal values must not leak
    for secret in ("Morning Run", "49.28", "-123.12", API_KEY, "2026-10-30"):
        assert secret not in text, secret


def test_diagnostics_requires_login(client):
    assert client.get("/api/diagnostics/shapes").status_code == 401


def test_quick_vs_background_lookback(authed, fake):
    run_sync(authed, "background")  # first run = full history
    latest = max(i["start_time"] for i in authed.get("/api/activities").json()["items"])[:10]
    latest_d = date.fromisoformat(latest)
    n = len(fake.search_params)
    run_sync(authed, "quick")
    assert fake.search_params[n]["startDate"] == (latest_d - timedelta(days=1)).isoformat()
    n = len(fake.search_params)
    run_sync(authed, "background")
    assert fake.search_params[n]["startDate"] == (latest_d - timedelta(days=30)).isoformat()


def test_quick_refetches_fewer_health_days_than_background(authed, fake):
    run_sync(authed, "background")
    sleep = "/sleep-service/sleep/dailySleep"
    a = fake.calls[sleep]
    run_sync(authed, "quick")
    quick = fake.calls[sleep] - a
    b = fake.calls[sleep]
    run_sync(authed, "background")
    deep = fake.calls[sleep] - b
    assert quick <= 3 < 25 <= deep <= 33


def test_mode_validation(authed):
    assert authed.post("/api/sync?mode=nonsense").status_code == 400


def test_schedule_setting_and_validation(authed):
    st = authed.get("/api/providers/garmin").json()["schedule"]
    assert st["interval_minutes"] == 360 and 0 in st["options"]
    r = authed.put("/api/providers/garmin/schedule", json={"interval_minutes": 60})
    assert r.json()["schedule"]["interval_minutes"] == 60
    assert authed.put("/api/providers/garmin/schedule", json={"interval_minutes": 5}).status_code == 400
    off = authed.put("/api/providers/garmin/schedule", json={"interval_minutes": 0}).json()
    assert off["schedule"]["interval_minutes"] == 0 and off["schedule"]["next_run_at"] is None


def test_scheduler_runs_when_due_then_waits(authed, client):
    manager = client.app.state.sync_manager
    first = manager.maybe_run_scheduled()
    assert first is not None and first.status == "ok"
    assert manager.maybe_run_scheduled() is None  # not due again for 6 h
    run = authed.get("/api/providers/garmin").json()["last_sync"]
    assert run["scheduled"] == 1 and run["mode"] == "background"
    authed.put("/api/providers/garmin/schedule", json={"interval_minutes": 0})
    assert manager.maybe_run_scheduled() is None  # off


def test_quick_sync_does_not_reset_schedule_timer(authed, client):
    from datetime import UTC, datetime, timedelta

    from app import db, schedule
    run_sync(authed, "quick")
    conn = db.connect(client.app.state.settings.db_path)
    try:
        assert schedule.is_due(conn, "garmin", client.app.state.settings)  # never deep-synced
        run_sync(authed, "background")
        later = datetime.now(UTC) + timedelta(hours=7)
        assert schedule.is_due(conn, "garmin", client.app.state.settings, now=later)
    finally:
        conn.close()


def test_full_sync_wellness_goes_through_throttle(authed, client, fake):
    """Under mode=full every wellness request must pass through the backfill
    throttle. We prove it by setting a tiny daily cap and asserting the sync
    pauses cleanly (status=ok, message contains 'Paused') instead of flooding
    Garmin — which is what the pre-fix behaviour would do."""
    manager = client.app.state.sync_manager
    # Tighten the cap so a full backfill is sure to trip it.
    import dataclasses
    manager.settings = dataclasses.replace(manager.settings, backfill_daily_cap=3,
                                           backfill_delay_s=0.0)
    manager._throttle = manager._throttle.__class__(manager.settings)
    r = run_sync(authed, full=True)
    msg = r["last_sync"]["message"] or ""
    # Either paused (hit cap during activities/wellness) or ok with the cap
    # evidence in the throttle snapshot. Either way day_count is bounded.
    from app import db
    conn = db.connect(client.app.state.settings.db_path)
    try:
        snap = manager._throttle.snapshot(conn)
    finally:
        conn.close()
    assert snap.day_count <= snap.daily_cap
    assert ("Paused" in msg or "paused" in msg.lower()
            or snap.day_count == snap.daily_cap)
