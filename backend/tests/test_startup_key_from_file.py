"""P1: the Garmin key is loaded from a runtime secret file at startup.

Mirrors the Mini-side launcher behaviour: write a key file, point
``AEC_GARMIN_API_KEY_FILE`` at it (via Settings), and verify the app starts
with a configured, file-sourced credential that drives a real sync.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import Settings
from app.garmin.client import GarminClient
from app.main import create_app
from tests.conftest import API_KEY, FakeGarmin


def _app(settings, fake):
    def factory(api_key, base_url):
        return GarminClient(api_key, base_url, transport=httpx.MockTransport(fake.handler))
    return create_app(settings, factory, start_scheduler=False)


@pytest.fixture
def key_file(tmp_path):
    path = tmp_path / "garmin_api_key"
    path.write_text(API_KEY + "\n", encoding="utf-8")
    return path


def test_configured_from_file_at_startup(tmp_path, key_file):
    settings = Settings(data_dir=tmp_path / "data", request_delay_s=0, garmin_api_key_file=key_file)
    fake = FakeGarmin()
    app = _app(settings, fake)
    with TestClient(app, headers={"X-Requested-With": "aec"}) as c:
        c.post("/api/setup", json={"username": "admin", "password": "correct horse battery"})
        status = c.get("/api/providers/garmin").json()
        assert status["configured"] is True
        assert status["credential_source"] == "file"
        assert status["file_path"] == str(key_file)
        # sync must succeed using the file-sourced key
        assert c.post("/api/sync").status_code == 202
        import time
        for _ in range(200):
            s = c.get("/api/providers/garmin").json()
            if s["last_sync"] and s["last_sync"]["status"] in ("ok", "error"):
                break
            time.sleep(0.05)
        assert s["last_sync"]["status"] == "ok"
        assert s["last_sync"]["new_activities"] == 2


def test_key_reload_picks_up_new_file_contents(tmp_path, key_file):
    """Rotating the file + restart (new app) switches the key used for sync."""
    settings = Settings(data_dir=tmp_path / "data", request_delay_s=0, garmin_api_key_file=key_file)
    fake = FakeGarmin(valid_key="rotated-key-xyz")
    key_file.write_text("rotated-key-xyz\n", encoding="utf-8")
    app = _app(settings, fake)
    with TestClient(app, headers={"X-Requested-With": "aec"}) as c:
        c.post("/api/setup", json={"username": "admin", "password": "correct horse battery"})
        assert c.get("/api/providers/garmin").json()["configured"] is True
        assert c.post("/api/sync").status_code == 202
        import time
        for _ in range(200):
            s = c.get("/api/providers/garmin").json()
            if s["last_sync"] and s["last_sync"]["status"] in ("ok", "error"):
                break
            time.sleep(0.05)
        assert s["last_sync"]["status"] == "ok"
