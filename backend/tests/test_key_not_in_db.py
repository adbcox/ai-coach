"""P1: the Garmin key is NEVER persisted to the database in the file-source
mode. secret_enc stays NULL, and the key string does not appear in any file
under data_dir (db, wal, shm, backups, activity payloads)."""

from __future__ import annotations

import time

import httpx
import pytest
from fastapi.testclient import TestClient

from app import db
from app.config import Settings
from app.garmin.client import GarminClient
from app.main import create_app
from tests.conftest import API_KEY, FakeGarmin


@pytest.fixture
def running_app(tmp_path):
    key_file = tmp_path / "garmin_api_key"
    key_file.write_text(API_KEY + "\n", encoding="utf-8")
    settings = Settings(
        data_dir=tmp_path / "data", request_delay_s=0, garmin_api_key_file=key_file,
    )
    fake = FakeGarmin()

    def factory(api_key, base_url):
        return GarminClient(api_key, base_url, transport=httpx.MockTransport(fake.handler))

    app = create_app(settings, factory, start_scheduler=False)
    with TestClient(app, headers={"X-Requested-With": "aec"}) as c:
        c.post("/api/setup", json={"username": "admin", "password": "correct horse battery"})
        yield c, settings, key_file


def test_secret_enc_is_null_in_file_mode(running_app):
    c, settings, _key_file = running_app
    conn = db.connect(settings.db_path)
    try:
        row = conn.execute(
            "SELECT secret_enc, credential_source, file_path FROM provider_credentials "
            "WHERE provider='garmin'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    assert row["secret_enc"] is None
    assert row["credential_source"] == "file"
    assert row["file_path"].endswith("garmin_api_key")


def test_key_absent_from_all_data_files_after_sync(running_app):
    c, settings, key_file = running_app
    # run a full sync so the DB, WAL and activity payloads are all touched
    assert c.post("/api/sync").status_code == 202
    for _ in range(200):
        s = c.get("/api/providers/garmin").json()
        if s["last_sync"] and s["last_sync"]["status"] in ("ok", "error"):
            break
        time.sleep(0.05)
    assert s["last_sync"]["status"] == "ok"
    needle = API_KEY.encode()
    for path in settings.data_dir.rglob("*"):
        if not path.is_file():
            continue
        # the master key is binary; skip it (not a place we'd put a plain key)
        if path.name == "master.key":
            continue
        # the key file we *expect* to contain the key is outside data_dir
        assert needle not in path.read_bytes(), f"key string leaked into {path}"


def test_no_encrypted_blob_written_even_after_sync(running_app):
    c, settings, _ = running_app
    c.post("/api/sync")
    for _ in range(200):
        s = c.get("/api/providers/garmin").json()
        if s["last_sync"] and s["last_sync"]["status"] in ("ok", "error"):
            break
        time.sleep(0.05)
    conn = db.connect(settings.db_path)
    try:
        row = conn.execute(
            "SELECT secret_enc FROM provider_credentials WHERE provider='garmin'"
        ).fetchone()
    finally:
        conn.close()
    assert row["secret_enc"] is None
