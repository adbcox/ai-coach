import base64
import json
import time

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
        self.downloads = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/personal-api-key/token"):
            if request.headers.get("authorization") != f"ApiKey {self.valid_key}":
                return httpx.Response(401)
            return httpx.Response(200, text=make_jwt(time.time() + 86400))
        if not request.headers.get("authorization", "").startswith("Bearer "):
            return httpx.Response(401)
        if path.endswith("/search/activities"):
            start = int(request.url.params.get("start", 0))
            limit = int(request.url.params.get("limit", 50))
            return httpx.Response(200, json=self.activities[start:start + limit])
        if "/download-service/files/activity/" in path:
            self.downloads += 1
            return httpx.Response(200, content=make_zip(make_fit()))
        return httpx.Response(404)


@pytest.fixture
def fake():
    return FakeGarmin()


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path, request_delay_s=0, sync_interval_hours=0)


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
