"""P1: when the launcher has not injected the key file, sync must fail with a
clear, launcher-pointing error (no crash, no silent partial run)."""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.garmin.client import GarminClient
from app.main import create_app
from tests.conftest import FakeGarmin


def _client(settings, fake):
    def factory(api_key, base_url):
        return GarminClient(api_key, base_url, transport=httpx.MockTransport(fake.handler))
    app = create_app(settings, factory, start_scheduler=False)
    return TestClient(app, headers={"X-Requested-With": "aec"})


def test_missing_key_file_blocks_sync(tmp_path):
    missing = tmp_path / "does-not-exist"  # file never written
    settings = Settings(
        data_dir=tmp_path / "data", request_delay_s=0, garmin_api_key_file=missing,
    )
    fake = FakeGarmin()
    with _client(settings, fake) as c:
        c.post("/api/setup", json={"username": "admin", "password": "correct horse battery"})
        status = c.get("/api/providers/garmin").json()
        # no key file: no row inserted, so provider is unconfigured
        assert status["configured"] is False
        assert status["credential_source"] is None
        # starting a sync without a credential row is a 400
        r = c.post("/api/sync")
        assert r.status_code == 400


def test_empty_key_file_blocks_sync(tmp_path):
    empty = tmp_path / "garmin_api_key"
    empty.write_text("   \n", encoding="utf-8")  # whitespace only
    settings = Settings(
        data_dir=tmp_path / "data", request_delay_s=0, garmin_api_key_file=empty,
    )
    fake = FakeGarmin()
    with _client(settings, fake) as c:
        c.post("/api/setup", json={"username": "admin", "password": "correct horse battery"})
        status = c.get("/api/providers/garmin").json()
        assert status["configured"] is False
        assert c.post("/api/sync").status_code == 400


def test_file_source_without_runtime_secret_returns_clear_error(tmp_path):
    """A provider_credentials row with credential_source='file' but an empty
    runtime_secrets map (file vanished between startups) must surface a clear
    error message pointing at coach-start.sh, not a stack trace."""
    data_dir = tmp_path / "data"
    settings = Settings(data_dir=data_dir, request_delay_s=0)
    fake = FakeGarmin()
    # seed a file-sourced credential row directly, without a runtime secret
    from app import db
    db.init_db(settings.db_path)
    conn = db.connect(settings.db_path)
    conn.execute(
        "INSERT INTO provider_credentials (provider, secret_enc, updated_at, "
        "credential_source, file_path) VALUES (?, NULL, ?, 'file', ?)",
        ("garmin", "2026-11-04T00:00:00+00:00", str(tmp_path / "gone")),
    )
    conn.commit()
    conn.close()
    with _client(settings, fake) as c:
        c.post("/api/setup", json={"username": "admin", "password": "correct horse battery"})
        r = c.post("/api/sync")
        assert r.status_code == 202  # started; failure is reported in sync status
        import time
        for _ in range(200):
            s = c.get("/api/providers/garmin").json()
            if s["last_sync"] and s["last_sync"]["status"] in ("ok", "error"):
                break
            time.sleep(0.05)
        assert s["last_sync"]["status"] == "error"
        assert "coach-start.sh" in s["last_sync"]["message"]
