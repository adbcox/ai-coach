from datetime import date, timedelta

import httpx
import pytest

from app.garmin.client import GarminClient, GarminError
from app.wellness import CHUNK_DAYS, RECENT_CHUNKS, RECENT_DAYS, is_empty
from tests.conftest import API_KEY
from tests.test_api import wait_idle


def run_sync(client, full=False):
    assert client.post(f"/api/sync?full={'true' if full else 'false'}").status_code == 202
    return wait_idle(client)


def test_is_empty():
    assert is_empty(None) and is_empty([]) and is_empty({"data": []}) and is_empty({"a": {"b": None}})
    assert not is_empty({"data": [{"x": 1}]}) and not is_empty(0)


def test_first_sync_pulls_all_history_then_goes_incremental(authed, fake):
    authed.put("/api/providers/garmin", json={"api_key": API_KEY})
    run_sync(authed)
    first = fake.search_params[0]
    assert "startDate" not in first and "endDate" not in first  # no date filter: everything
    n = len(fake.search_params)
    run_sync(authed)
    assert "startDate" in fake.search_params[n]  # backfill done -> incremental window


def test_health_data_collected_and_not_refetched(authed, fake):
    authed.put("/api/providers/garmin", json={"api_key": API_KEY})
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
    run_sync(authed)
    assert fake.calls[summ] - before_s <= RECENT_CHUNKS
    assert fake.calls[sleep] - before_d <= RECENT_DAYS
    # a full re-scan only fills gaps, it does not refetch stored history
    run_sync(authed, full=True)
    assert fake.calls[sleep] - before_d < 30


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
