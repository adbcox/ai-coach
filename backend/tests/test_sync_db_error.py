"""The sync thread must mark a run failed when the DB is corrupt, not wedge
inside sqlite's C extension. See P1-REPORT 2026-11-05 post-mortem."""

from __future__ import annotations

import sqlite3

import pytest

from app import db, sync
from app.crypto import SecretBox
from app.sync import PROVIDER, SyncManager
from tests.conftest import API_KEY


@pytest.fixture
def fresh_db(settings):
    db.init_db(settings.db_path)
    conn = db.connect(settings.db_path)
    conn.execute(
        "INSERT INTO provider_credentials (provider, secret_enc, updated_at, "
        "credential_source, file_path) VALUES (?, NULL, ?, 'file', ?)",
        (PROVIDER, "2026-11-05T00:00:00+00:00", str(settings.garmin_api_key_file)),
    )
    conn.commit()
    conn.close()
    return settings


def test_db_error_during_activities_marks_run_failed(fresh_db, monkeypatch):
    """A DatabaseError raised anywhere inside _sync() (simulated here at the
    _sync_activities entry point) must turn into a failed SyncResult and
    release the lock, NOT hang the thread."""
    box = SecretBox.load(fresh_db.secrets_dir, None)
    manager = SyncManager(fresh_db, box, runtime_secrets={PROVIDER: API_KEY})

    def boom(*a, **kw):
        raise sqlite3.DatabaseError("database disk image is malformed")

    monkeypatch.setattr(manager, "_sync_activities", boom)
    # bypass the network path — ensure_token is called before _sync_activities
    monkeypatch.setattr("app.garmin.client.GarminClient.ensure_token",
                        lambda self: None)
    result = manager.run_once(mode="quick")
    assert result.status == "error"
    assert "Database error during sync" in result.message
    assert "disk image is malformed" in result.message
    assert manager.running is False  # lock released

    conn = db.connect(fresh_db.db_path)
    row = conn.execute(
        "SELECT status, finished_at, message FROM sync_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    assert row["status"] == "error"
    assert row["finished_at"] is not None
    assert "Database error during sync" in row["message"]
