import io
import tarfile
import threading

import pytest
from fastapi.testclient import TestClient

from app import backup, db
from app.config import Settings
from app.main import create_app
from tests.conftest import API_KEY, FakeGarmin
from tests.test_api import wait_idle

PASS = "correct horse battery"


def make_client(tmp_path, fake=None):
    import httpx

    from app.garmin.client import GarminClient
    fake = fake or FakeGarmin()
    key_file = tmp_path / "garmin_api_key"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    key_file.write_text(API_KEY + "\n", encoding="utf-8")
    settings = Settings(data_dir=tmp_path, request_delay_s=0, garmin_api_key_file=key_file)
    app = create_app(settings, lambda k, u: GarminClient(k, u, transport=httpx.MockTransport(fake.handler)),
                     start_scheduler=False)
    return TestClient(app, headers={"X-Requested-With": "aec"}), settings


def wait_backup(client):
    import time
    end = time.time() + 15
    while time.time() < end:
        s = client.get("/api/backups").json()
        if not s["running"]:
            return s
        time.sleep(0.05)
    raise AssertionError("backup did not finish")


@pytest.fixture
def populated(tmp_path):
    client, settings = make_client(tmp_path / "src")
    with client:
        client.post("/api/setup", json={"username": "admin", "password": PASS})
        client.post("/api/sync?mode=background")
        wait_idle(client)
        yield client, settings


def names(path):
    with tarfile.open(path) as t:
        return t.getnames()


def test_backup_contents_and_no_master_key(populated):
    client, settings = populated
    client.post("/api/backups", json={})
    s = wait_backup(client)
    assert s["error"] is None and len(s["items"]) == 1
    path = backup.backup_dir(settings) / s["items"][0]["name"]
    n = names(path)
    assert "manifest.json" in n and "db/coach.sqlite3.gz" in n
    assert any(x.startswith("activities/garmin/") for x in n)
    assert "secrets.enc" not in n
    assert not any("master.key" in x or "secrets/" in x for x in n)
    assert API_KEY.encode() not in path.read_bytes()


def test_backup_with_passphrase_omits_file_sourced_key(populated):
    """P1: the Garmin key is file-sourced from Infisical; it is never written
    to the backup, even when a passphrase would normally seal secrets."""
    client, settings = populated
    client.post("/api/backups", json={"passphrase": "pass-phrase-123"})
    s = wait_backup(client)
    path = backup.backup_dir(settings) / s["items"][0]["name"]
    assert "secrets.enc" not in names(path)
    assert API_KEY.encode() not in path.read_bytes()


def test_download_delete_and_name_validation(populated):
    client, _ = populated
    client.post("/api/backups", json={})
    name = wait_backup(client)["items"][0]["name"]
    r = client.get(f"/api/backups/{name}")
    assert r.status_code == 200 and r.content[:1] != b""
    assert client.get("/api/backups/..%2Fetc%2Fpasswd").status_code == 404
    assert client.get("/api/backups/not-a-backup.tar").status_code == 404
    assert client.delete(f"/api/backups/{name}").status_code == 200
    assert client.get("/api/backups").json()["items"] == []


def test_restore_onto_fresh_install_with_file_sourced_key(populated, tmp_path):
    """P1: a fresh host restores activities + user, but the Garmin key is
    re-provisioned by the Mini-side launcher (same key file), so the restored
    install is configured and syncable without any passphrase gymnastics."""
    client, _ = populated
    client.post("/api/backups", json={"passphrase": "pass-phrase-123"})
    name = wait_backup(client)["items"][0]["name"]
    data = client.get(f"/api/backups/{name}").content

    fresh, fsettings = make_client(tmp_path / "dst")
    with fresh:
        assert fresh.get("/api/session").json()["setup_required"]
        ok = fresh.put("/api/restore", content=data, headers={"X-Passphrase": "pass-phrase-123"})
        assert ok.status_code == 200, ok.text
        body = ok.json()
        assert body["rows"]["activities"] == 2
        # file-source credential is not in the backup; secrets_restored is False
        assert body["secrets_restored"] is False
        assert not fresh.get("/api/session").json()["setup_required"]
        assert fresh.post("/api/login", json={"username": "admin", "password": PASS}).status_code == 200
        assert fresh.get("/api/activities").json()["total"] == 2
        # the launcher-provisioned key file on the fresh host makes it configured
        assert fresh.get("/api/providers/garmin").json()["configured"] is True
        assert (fsettings.data_dir / "activities" / "garmin" / "111.zip").exists()
        fresh.post("/api/sync?mode=background")
        assert wait_idle(fresh)["last_sync"]["status"] == "ok"


def test_restore_without_passphrase_still_works_in_file_mode(populated, tmp_path):
    """Without a passphrase the backup has no secrets.enc anyway (file mode);
    restore proceeds, and the launcher-provisioned key makes the host usable."""
    client, _ = populated
    client.post("/api/backups", json={"passphrase": "pass-phrase-123"})
    data = client.get("/api/backups/" + wait_backup(client)["items"][0]["name"]).content
    fresh, _ = make_client(tmp_path / "dst2")
    with fresh:
        r = fresh.put("/api/restore", content=data)
        assert r.status_code == 200 and r.json()["secrets_restored"] is False
        assert r.json()["secrets_in_backup"] is False  # file-source backup has no sealed blob
        fresh.post("/api/login", json={"username": "admin", "password": PASS})
        # the fresh install's launcher has already written a key file, so configured
        assert fresh.get("/api/providers/garmin").json()["configured"] is True


def test_restore_requires_login_once_installed_and_keeps_old_db(populated):
    client, settings = populated
    client.post("/api/backups", json={})
    data = client.get("/api/backups/" + wait_backup(client)["items"][0]["name"]).content
    anon = TestClient(client.app, headers={"X-Requested-With": "aec"})
    assert anon.put("/api/restore", content=data).status_code == 401
    r = client.put("/api/restore", content=data)
    assert r.status_code == 200 and r.json()["previous_database_kept_as"].startswith("pre-restore-")
    assert (settings.db_path.parent / r.json()["previous_database_kept_as"]).exists()
    # sessions are not in a backup: you are signed out after a restore
    assert client.get("/api/session").json()["authenticated"] is False


def test_restore_refused_while_sync_running(populated):
    client, _ = populated
    client.post("/api/backups", json={})
    data = client.get("/api/backups/" + wait_backup(client)["items"][0]["name"]).content
    mgr = client.app.state.sync_manager
    assert mgr.try_exclusive()
    try:
        assert client.put("/api/restore", content=data).status_code == 409
    finally:
        mgr.release_exclusive()


def _tar_with(member_name: str, payload=b"x") -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as t:
        info = tarfile.TarInfo(member_name)
        info.size = len(payload)
        t.addfile(info, io.BytesIO(payload))
    return buf.getvalue()


@pytest.mark.parametrize("name", ["../evil", "/etc/passwd", "activities/../../evil", "other/file"])
def test_malicious_archives_rejected(tmp_path, name):
    client, settings = make_client(tmp_path)
    with client:
        r = client.put("/api/restore", content=_tar_with(name))
        assert r.status_code == 400
        assert not (tmp_path.parent / "evil").exists()


def test_not_a_backup_and_newer_schema_rejected(tmp_path):
    import json
    client, _ = make_client(tmp_path)
    with client:
        assert client.put("/api/restore", content=b"garbage").status_code == 400
        manifest = json.dumps({"format": 1, "schema_version": db.SCHEMA_VERSION + 1}).encode()
        r = client.put("/api/restore", content=_tar_with("manifest.json", manifest))
        assert r.status_code == 400 and "newer" in r.json()["detail"]


def test_prune_keeps_newest(tmp_path):
    settings = Settings(data_dir=tmp_path)
    d = backup.backup_dir(settings)
    d.mkdir(parents=True)
    for i in range(5):
        (d / f"ai-endurance-coach-backup-2026010{i}-000000.tar").write_bytes(b"x")
    backup.prune(settings, 2)
    assert [b["name"][-19:-4] for b in backup.list_backups(settings)] == ["20260104-000000", "20260103-000000"]


def test_backup_while_syncing_is_consistent(populated):
    client, _ = populated
    barrier = threading.Event()

    def sync():
        client.post("/api/sync?mode=background")
        barrier.set()

    threading.Thread(target=sync).start()
    barrier.wait(5)
    client.post("/api/backups", json={})
    assert wait_backup(client)["error"] is None
