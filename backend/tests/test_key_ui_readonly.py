"""P1: the Garmin key UI is read-only. PUT and DELETE return 405 with a
message that points the user at the launcher (Infisical rotation)."""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.garmin.client import GarminClient
from app.main import create_app
from tests.conftest import API_KEY, FakeGarmin


@pytest.fixture
def unconfigured(tmp_path):
    """A running app with NO Garmin key file wired in — so the only way to
    configure a key would be via the UI, which must now be rejected."""
    settings = Settings(data_dir=tmp_path, request_delay_s=0)  # no key file
    fake = FakeGarmin()

    def factory(api_key, base_url):
        return GarminClient(api_key, base_url, transport=httpx.MockTransport(fake.handler))

    app = create_app(settings, factory, start_scheduler=False)
    with TestClient(app, headers={"X-Requested-With": "aec"}) as c:
        c.post("/api/setup", json={"username": "admin", "password": "correct horse battery"})
        yield c, settings


def test_put_key_returns_405_and_does_not_store(unconfigured):
    c, _ = unconfigured
    r = c.put("/api/providers/garmin", json={"api_key": API_KEY})
    assert r.status_code == 405
    # response body must not echo the key, and must point to the launcher
    assert API_KEY not in r.text
    assert "Infisical" in r.text or "launcher" in r.text or "coach-start" in r.text
    # nothing was written: still unconfigured
    assert c.get("/api/providers/garmin").json()["configured"] is False


def test_delete_key_returns_405(unconfigured):
    c, _ = unconfigured
    r = c.delete("/api/providers/garmin")
    assert r.status_code == 405
    assert "Infisical" in r.text or "launcher" in r.text or "coach-start" in r.text


def test_put_key_leaves_db_empty(unconfigured):
    """Even after a 405, inspect the DB directly and confirm no row was written."""
    c, settings = unconfigured
    c.put("/api/providers/garmin", json={"api_key": API_KEY})
    from app import db
    conn = db.connect(settings.db_path)
    try:
        row = conn.execute(
            "SELECT * FROM provider_credentials WHERE provider='garmin'"
        ).fetchone()
    finally:
        conn.close()
    assert row is None
