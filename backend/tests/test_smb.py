import os
import sys
import types
from pathlib import Path

import pytest

from app import backup, smb
from tests.conftest import API_KEY
from tests.test_api import wait_idle
from tests.test_backup import make_client, wait_backup


class FakeSmbModule(types.ModuleType):
    """smbclient imitation backed by a local folder: \\\\host\\share\\x -> root/share/x."""

    def __init__(self, root: Path, user="backup", password="pw", shares=("BK",), fail_upload=False):
        super().__init__("smbclient")
        self.root, self.user, self.password = root, user, password
        self.shares, self.fail_upload = shares, fail_upload
        self.sessions = []

    def _local(self, unc: str) -> Path:
        parts = [p for p in unc.split("\\") if p]
        _host, share, rest = parts[0], parts[1], parts[2:]
        if share not in self.shares:
            raise OSError("[NtStatus 0xc00000cc] STATUS_BAD_NETWORK_NAME")
        return self.root.joinpath(share, *rest)

    def register_session(self, host, username, password, port, connection_timeout):
        self.sessions.append((host, username, port))
        if username.split("\\")[-1] != self.user or password != self.password:
            raise OSError("LogonFailure: STATUS_LOGON_FAILURE")

    def makedirs(self, path, exist_ok=False, port=445):
        self._local(path).mkdir(parents=True, exist_ok=exist_ok)

    def open_file(self, path, mode="rb", port=445):
        p = self._local(path)
        handle = open(p, mode)
        if self.fail_upload and "w" in mode and p.name.endswith(".tar"):
            real_write = handle.write
            handle.write = lambda data: real_write(data[: len(data) // 2])  # truncate
        return handle

    def stat(self, path, port=445):
        return self._local(path).stat()

    def remove(self, path, port=445):
        self._local(path).unlink()

    def listdir(self, path, port=445):
        return os.listdir(self._local(path))


@pytest.fixture
def share(tmp_path, monkeypatch):
    fake = FakeSmbModule(tmp_path / "server")
    (tmp_path / "server" / "BK").mkdir(parents=True)
    monkeypatch.setitem(sys.modules, "smbclient", fake)
    return fake


GOOD = {"host": "nas.local", "share": "BK", "folder": "coach", "username": "backup",
        "password": "pw", "interval_minutes": 1440, "keep": 2}


def target(**kw):
    d = {"host": "nas.local", "share": "BK", "folder": "coach", "username": "backup", "password": "pw"}
    d.update(kw)
    return smb.SmbTarget(**d)


@pytest.mark.parametrize("kw", [
    {"folder": "../etc"}, {"folder": "a/../b"}, {"host": "a/b"}, {"host": ""}, {"share": "a\\b"},
    {"share": ""}, {"username": ""}, {"port": 0}])
def test_validation_rejects_bad_input(kw):
    with pytest.raises(smb.SmbError):
        smb.validate(target(**kw))


def test_check_connection_ok_and_leaves_no_probe_file(share):
    smb.check_connection(target())
    assert list((share.root / "BK" / "coach").iterdir()) == []


def test_friendly_errors(share):
    with pytest.raises(smb.SmbError, match="username or password"):
        smb.check_connection(target(password="nope"))
    with pytest.raises(smb.SmbError, match="not found"):
        smb.check_connection(target(share="MISSING"))


def test_upload_verify_and_prune(share, tmp_path):
    for i in range(4):
        f = tmp_path / f"ai-endurance-coach-backup-2026010{i}-000000.tar"
        f.write_bytes(b"x" * (100 + i))
        assert smb.upload(target(), f) == 100 + i
    assert len(smb.list_remote(target())) == 4
    assert smb.prune_remote(target(), 2) == 2
    names = [e["name"] for e in smb.list_remote(target())]
    assert names == ["ai-endurance-coach-backup-20260103-000000.tar",
                     "ai-endurance-coach-backup-20260102-000000.tar"]


def test_upload_refuses_non_backup_files(share, tmp_path):
    f = tmp_path / "secrets.txt"
    f.write_text("x")
    with pytest.raises(smb.SmbError):
        smb.upload(target(), f)


def test_partial_upload_is_detected_and_removed(tmp_path, monkeypatch):
    fake = FakeSmbModule(tmp_path / "server", fail_upload=True)
    (tmp_path / "server" / "BK").mkdir(parents=True)
    monkeypatch.setitem(sys.modules, "smbclient", fake)
    f = tmp_path / "ai-endurance-coach-backup-20260101-000000.tar"
    f.write_bytes(b"x" * 1000)
    with pytest.raises(smb.SmbError, match="incomplete"):
        smb.upload(target(), f)
    assert list((tmp_path / "server" / "BK" / "coach").iterdir()) == []


def test_prune_only_touches_backup_named_files(share, tmp_path):
    folder = share.root / "BK" / "coach"
    folder.mkdir(parents=True)
    (folder / "family-photos.tar").write_bytes(b"keep me")
    for i in range(3):
        (folder / f"ai-endurance-coach-backup-2026010{i}-000000.tar").write_bytes(b"x")
    smb.prune_remote(target(), 1)
    assert (folder / "family-photos.tar").exists()
    assert len(list(folder.glob("ai-endurance-coach-backup-*"))) == 1


# ------------------------------------------------------------------ through the API
@pytest.fixture
def app_with_share(tmp_path, share):
    client, settings = make_client(tmp_path / "app")
    with client:
        client.post("/api/setup", json={"username": "admin", "password": "correct horse battery"})
        yield client, settings, share


def test_api_saves_target_encrypted_and_never_returns_password(app_with_share):
    client, settings, share = app_with_share
    secret = "long-share-password-9"
    share.password = secret
    r = client.put("/api/backups/smb", json={**GOOD, "password": secret})
    assert r.status_code == 200 and r.json()["configured"]
    assert secret not in r.text and "password" not in r.json()
    assert secret not in client.get("/api/backups").text
    for path in settings.data_dir.rglob("*"):
        if path.is_file() and path.name != "master.key":
            assert secret.encode() not in path.read_bytes(), path


def test_api_bad_credentials_not_saved(app_with_share):
    client, _, _ = app_with_share
    r = client.put("/api/backups/smb", json={**GOOD, "password": "wrong"})
    assert r.status_code == 400 and "username or password" in r.json()["detail"]
    assert client.get("/api/backups").json()["smb"]["configured"] is False


def test_api_password_kept_when_omitted_and_removal(app_with_share):
    client, _, _ = app_with_share
    client.put("/api/backups/smb", json=GOOD)
    upd = {k: v for k, v in GOOD.items() if k != "password"} | {"keep": 5}
    r = client.put("/api/backups/smb", json=upd)
    assert r.status_code == 200 and r.json()["keep"] == 5
    assert client.delete("/api/backups/smb").json()["configured"] is False


def test_manual_backup_uploads_and_prunes_remote(app_with_share):
    client, settings, share = app_with_share
    client.put("/api/backups/smb", json=GOOD)  # keep=2
    import time
    for _ in range(3):
        client.post("/api/backups", json={})
        wait_backup(client)
        time.sleep(1.1)  # distinct timestamps
    remote = sorted((share.root / "BK" / "coach").glob("ai-endurance-coach-backup-*.tar"))
    assert len(remote) == 2
    st = client.get("/api/backups").json()["smb"]
    assert st["last_status"] == "ok" and "Uploaded" in st["last_message"]


def test_share_failure_keeps_local_backup_and_reports(app_with_share):
    client, settings, share = app_with_share
    client.put("/api/backups/smb", json=GOOD)
    share.password = "changed-on-server"  # credentials stop working
    client.post("/api/backups", json={})
    s = wait_backup(client)
    assert len(s["items"]) == 1  # local copy exists
    assert "share upload failed" in s["error"]
    assert s["smb"]["last_status"] == "error"


def test_scheduler_runs_when_due_then_waits_and_skips_when_manual_only(app_with_share):
    client, settings, share = app_with_share
    mgr = client.app.state.backup_manager
    assert mgr.maybe_run_scheduled() is False  # no target
    client.put("/api/backups/smb", json=GOOD)
    assert mgr.maybe_run_scheduled() is True  # never run -> due
    assert mgr.maybe_run_scheduled() is False  # not due for a day
    assert len(list((share.root / "BK" / "coach").glob("*.tar"))) == 1
    client.put("/api/backups/smb", json={**GOOD, "interval_minutes": 0})
    from app import db
    conn = db.connect(settings.db_path)
    conn.execute("UPDATE backup_target SET last_run_at=NULL")
    conn.commit()
    conn.close()
    assert mgr.maybe_run_scheduled() is False  # interval 0 = manual only


def test_scheduled_backup_never_includes_the_garmin_key(app_with_share):
    import tarfile
    client, settings, share = app_with_share
    client.put("/api/backups/smb", json=GOOD)
    client.app.state.backup_manager.maybe_run_scheduled()
    tar_path = next((share.root / "BK" / "coach").glob("*.tar"))
    with tarfile.open(tar_path) as t:
        assert "secrets.enc" not in t.getnames()
    assert API_KEY.encode() not in tar_path.read_bytes()


def test_sync_still_works_alongside_backups(app_with_share):
    client, _, _ = app_with_share
    client.post("/api/sync?mode=background")
    assert wait_idle(client)["last_sync"]["status"] == "ok"
    assert backup is not None
