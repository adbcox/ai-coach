import base64
import collections
import json
import time
from datetime import date, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.garmin.client import GarminClient
from app.main import create_app
from tests.fitgen import make_fit, make_zip

API_KEY = "test-key-SECRET-1234567890"


def make_jwt(exp: float) -> str:
    def enc(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{enc({'alg': 'none'})}.{enc({'exp': exp})}.sig"


class FakeGarmin:
    """httpx transport imitating the Personal API endpoints we use."""

    def __init__(self, activities=None, valid_key=API_KEY):
        self.activities = activities if activities is not None else [
            {"activityId": 111, "activityName": "Morning Run",
             "activityType": {"typeKey": "running"}, "startTimeGMT": "2026-10-30 14:00:00"},
            {"activityId": 222, "activityName": "Ride",
             "activityType": {"typeKey": "cycling"}, "startTimeGMT": "2026-10-31 15:00:00"},
        ]
        self.valid_key = valid_key
        self.fit = make_fit  # tests swap this to serve FIT files with laps
        self.downloads = 0
        self.calls = collections.Counter()
        self.search_params = []
        self.data_since = (date.today() - timedelta(days=30)).isoformat()

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/personal-api-key/token"):
            if request.headers.get("authorization") != f"ApiKey {self.valid_key}":
                return httpx.Response(401)
            return httpx.Response(200, text=make_jwt(time.time() + 86400))
        if not request.headers.get("authorization", "").startswith("Bearer "):
            return httpx.Response(401)
        self.calls[path] += 1
        params = request.url.params
        if path.endswith("/dailysummaries"):
            has = params["endDate"] >= self.data_since
            item = {"calendarDate": params["endDate"], "movement": {"steps": {"value": 9000}},
                    "heartRate": {"restingValue": 50}, "stress": {"avgLevel": 25},
                    "bodyBattery": {"minValue": 20, "maxValue": 90}}
            return httpx.Response(200, json={"data": [item] if has else []})
        if path.endswith("/sleep-service/sleep/dailySleep"):
            has = params["date"] >= self.data_since
            body = {"calendarDate": params["date"], "sleepTimeSeconds": 27000, "deepSleepSeconds": 5400,
                    "remSleepSeconds": 5400, "lightSleepSeconds": 14400, "awakeSleepSeconds": 1800,
                    "sleepScores": {"overall": {"value": 80}}}
            null_day = {"calendarDate": params["date"], "sleepTimeSeconds": None, "deviceRemCapable": False}
            return httpx.Response(200, json=body if has else null_day)
        if path.endswith("/search/activities"):
            self.search_params.append(dict(params))
            start = int(request.url.params.get("start", 0))
            limit = int(request.url.params.get("limit", 50))
            return httpx.Response(200, json=self.activities[start:start + limit])
        if "/download-service/files/activity/" in path:
            self.downloads += 1
            return httpx.Response(200, content=make_zip(self.fit()))
        return httpx.Response(404)


@pytest.fixture
def fake():
    return FakeGarmin()


@pytest.fixture
def settings(tmp_path):
    # P1: by default give tests a runtime key file so the app behaves like it
    # does in production (key injected by the Mini-side launcher). Tests that
    # specifically need an *unconfigured* app override this fixture.
    key_file = tmp_path / "garmin_api_key"
    key_file.write_text(API_KEY + "\n", encoding="utf-8")
    # start == end disables the nightly backfill-window gate for tests so
    # they don't depend on wall-clock time. Window tests set this explicitly.
    # backfill_delay_s=0 so wellness (which now goes through the throttle on
    # full syncs) doesn't sleep between requests in tests.
    return Settings(data_dir=tmp_path, request_delay_s=0, garmin_api_key_file=key_file,
                    backfill_window_start="00:00", backfill_window_end="00:00",
                    backfill_delay_s=0.0)


@pytest.fixture
def client(settings, fake):
    def factory(api_key, base_url):
        return GarminClient(api_key, base_url, transport=httpx.MockTransport(fake.handler))
    app = create_app(settings, factory, start_scheduler=False)
    with TestClient(app, headers={"X-Requested-With": "aec"}) as c:
        yield c


@pytest.fixture
def authed(client):
    r = client.post("/api/setup", json={"username": "admin", "password": "correct horse battery"})
    assert r.status_code == 200
    return client
