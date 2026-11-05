"""Portable backup and restore.

A backup is a plain .tar containing:
  manifest.json             what it is (format, app + schema version, counts)
  db/coach.sqlite3.gz       consistent snapshot (SQLite online backup), sessions and
                            stored provider credentials removed
  activities/...            the original downloaded Garmin files
  ingest/...                ingest folders, if present
  secrets.enc               OPTIONAL: provider credentials sealed with a passphrase

The master key (secrets/master.key) is never included. Without a passphrase the
Garmin key is simply not in the backup; re-enter it after restoring.
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import io
import json
import os
import re
import shutil
import sqlite3
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from . import __version__, db
from .config import Settings
from .crypto import SecretBox

FORMAT = 1
NAME_RE = re.compile(r"^ai-endurance-coach-backup-\d{8}-\d{6}\.tar$")
DEFAULT_KEEP = 7
_ALLOWED_TOP = ("activities/", "ingest/")


class BackupError(Exception):
    pass


class RestoreError(Exception):
    pass


# ---------------------------------------------------------------- secrets sealing
def _kdf(passphrase: str, salt: bytes) -> bytes:
    raw = hashlib.scrypt(passphrase.encode(), salt=salt, n=2**15, r=8, p=1, dklen=32,
                         maxmem=128 * 1024 * 1024)
    return base64.urlsafe_b64encode(raw)


def seal_secrets(secrets: dict[str, str], passphrase: str) -> bytes:
    salt = os.urandom(16)
    token = Fernet(_kdf(passphrase, salt)).encrypt(json.dumps(secrets).encode())
    return json.dumps({"kdf": "scrypt", "salt": base64.b64encode(salt).decode(),
                       "token": token.decode()}).encode()


def open_secrets(blob: bytes, passphrase: str) -> dict[str, str]:
    try:
        meta = json.loads(blob)
        salt = base64.b64decode(meta["salt"])
        return json.loads(Fernet(_kdf(passphrase, salt)).decrypt(meta["token"].encode()))
    except (InvalidToken, ValueError, KeyError) as exc:
        raise RestoreError("Wrong passphrase, or the secrets file is damaged.") from exc


# ---------------------------------------------------------------- listing / pruning
def backup_dir(settings: Settings) -> Path:
    return settings.data_dir / "backups"


def list_backups(settings: Settings) -> list[dict[str, Any]]:
    d = backup_dir(settings)
    if not d.is_dir():
        return []
    out = []
    for f in sorted(d.iterdir(), reverse=True):
        if NAME_RE.match(f.name) and f.is_file():
            st = f.stat()
            out.append({"name": f.name, "size": st.st_size,
                        "created_at": datetime.fromtimestamp(st.st_mtime, UTC).isoformat(
                            timespec="seconds")})
    return out


def prune(settings: Settings, keep: int) -> None:
    for old in list_backups(settings)[max(1, keep):]:
        (backup_dir(settings) / old["name"]).unlink(missing_ok=True)


def resolve(settings: Settings, name: str) -> Path | None:
    """Safe lookup of a stored backup by name (no path tricks)."""
    if not NAME_RE.match(name):
        return None
    path = backup_dir(settings) / name
    return path if path.is_file() else None


# ---------------------------------------------------------------- create
def _add_bytes(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    info.mtime = int(datetime.now(UTC).timestamp())
    info.mode = 0o600
    tar.addfile(info, io.BytesIO(data))


def _walk_files(root: Path, prefix: str):
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink() and not path.name.endswith(".part"):
            yield path, f"{prefix}/{path.relative_to(root).as_posix()}"


def create_backup(settings: Settings, box: SecretBox, *, passphrase: str | None = None,
                  keep: int = DEFAULT_KEEP, extra_secrets: dict[str, str] | None = None) -> Path:
    d = backup_dir(settings)
    d.mkdir(parents=True, exist_ok=True)
    os.chmod(d, 0o700)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    final = d / f"ai-endurance-coach-backup-{stamp}.tar"
    part = final.with_name(final.name + ".part")
    tmp_root = settings.data_dir / "tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(dir=tmp_root, prefix="backup-"))
    try:
        snap = work / "coach.sqlite3"
        src = db.connect(settings.db_path)
        dst = sqlite3.connect(snap)
        try:
            src.backup(dst)  # consistent even while a sync is writing
        finally:
            src.close()
        dst.row_factory = sqlite3.Row
        secrets: dict[str, str] = dict(extra_secrets or {})
        if passphrase:
            # P1: file-source credentials have secret_enc=NULL; they live in
            # Infisical, not the DB, so they are never sealed into the backup.
            for row in dst.execute(
                "SELECT provider, secret_enc FROM provider_credentials WHERE secret_enc IS NOT NULL"
            ):
                try:
                    secrets[row["provider"]] = box.decrypt(row["secret_enc"])
                except ValueError:
                    pass
        counts = {t: dst.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: S608
                  for t in ("activities", "samples", "wellness_raw", "users")}
        dst.execute("DELETE FROM sessions")
        dst.execute("DELETE FROM provider_credentials")
        dst.commit()
        dst.close()

        gz = work / "coach.sqlite3.gz"
        with open(snap, "rb") as fi, gzip.open(gz, "wb", compresslevel=6) as fo:
            shutil.copyfileobj(fi, fo)

        files = list(_walk_files(settings.activities_dir, "activities"))
        files += list(_walk_files(settings.data_dir / "ingest", "ingest"))
        manifest = {
            "format": FORMAT, "app_version": __version__, "schema_version": db.SCHEMA_VERSION,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "includes": {"files": len(files), "secrets": bool(secrets and passphrase)},
            "rows": counts,
        }
        with tarfile.open(part, "w") as tar:
            _add_bytes(tar, "manifest.json", json.dumps(manifest, indent=1).encode())
            tar.add(gz, arcname="db/coach.sqlite3.gz")
            for path, arc in files:
                tar.add(path, arcname=arc, recursive=False)
            if secrets and passphrase:
                _add_bytes(tar, "secrets.enc", seal_secrets(secrets, passphrase))
        os.chmod(part, 0o600)
        os.replace(part, final)
    finally:
        shutil.rmtree(work, ignore_errors=True)
        part.unlink(missing_ok=True)
    prune(settings, keep)
    return final


# ---------------------------------------------------------------- restore
def _safe_member(member: tarfile.TarInfo) -> str:
    name = member.name
    if not member.isfile():
        raise RestoreError(f"Unexpected entry in backup: {name!r}")
    parts = Path(name).parts
    if name.startswith("/") or ".." in parts or "\\" in name:
        raise RestoreError(f"Unsafe path in backup: {name!r}")
    if name not in ("manifest.json", "secrets.enc", "db/coach.sqlite3.gz") and not name.startswith(
            _ALLOWED_TOP):
        raise RestoreError(f"Unexpected file in backup: {name!r}")
    return name


def restore_backup(settings: Settings, box: SecretBox, archive: Path, *,
                   passphrase: str | None = None) -> dict[str, Any]:
    tmp_root = settings.data_dir / "tmp"
    tmp_root.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(dir=tmp_root, prefix="restore-"))
    try:
        try:
            tar = tarfile.open(archive, "r")
        except tarfile.TarError as exc:
            raise RestoreError("That file is not a valid backup archive.") from exc
        manifest: dict[str, Any] | None = None
        secrets_blob: bytes | None = None
        staged: list[tuple[Path, str]] = []
        with tar:
            for member in tar:
                name = _safe_member(member)
                handle = tar.extractfile(member)
                assert handle is not None
                if name == "manifest.json":
                    manifest = json.loads(handle.read(1_000_000))
                elif name == "secrets.enc":
                    secrets_blob = handle.read(1_000_000)
                else:
                    target = stage / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with open(target, "wb") as out:
                        shutil.copyfileobj(handle, out)
                    staged.append((target, name))
        if not manifest or manifest.get("format") != FORMAT:
            raise RestoreError("Not a backup made by this app (missing or unknown manifest).")
        if int(manifest.get("schema_version", 0)) > db.SCHEMA_VERSION:
            raise RestoreError("This backup is from a newer version of the app. Update first.")
        gz = stage / "db" / "coach.sqlite3.gz"
        if not gz.is_file():
            raise RestoreError("The backup contains no database.")

        creds: dict[str, str] = {}
        secrets_restored = False
        if secrets_blob and passphrase:
            creds = open_secrets(secrets_blob, passphrase)  # raises on wrong passphrase
            secrets_restored = True

        new_db = stage / "coach.sqlite3"
        with gzip.open(gz, "rb") as fi, open(new_db, "wb") as fo:
            shutil.copyfileobj(fi, fo)
        check = sqlite3.connect(new_db)
        try:
            if check.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RestoreError("The backup's database failed its integrity check.")
        finally:
            check.close()
        db.init_db(new_db)  # upgrade an older schema in place
        conn = db.connect(new_db)
        try:
            conn.execute("DELETE FROM sessions")
            now = datetime.now(UTC).isoformat(timespec="seconds")
            for provider, secret in creds.items():
                conn.execute(
                    "INSERT OR REPLACE INTO provider_credentials (provider, secret_enc, "
                    "updated_at, validated_at) VALUES (?, ?, ?, NULL)",
                    (provider, box.encrypt(secret), now))
            conn.commit()
            summary_rows = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: S608
                            for t in ("activities", "samples", "wellness_raw", "users")}
            conn.commit()
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()

        # ---- point of no return: swap the database, keep the old one
        live = settings.db_path
        live.parent.mkdir(parents=True, exist_ok=True)
        kept = None
        if live.exists():
            old = db.connect(live)
            try:
                old.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                old.close()
            kept = live.with_name(
                f"pre-restore-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.sqlite3")
            os.replace(live, kept)
        for suffix in ("-wal", "-shm"):
            Path(str(live) + suffix).unlink(missing_ok=True)
        os.replace(new_db, live)

        restored_files = 0
        for path, name in staged:
            if name == "db/coach.sqlite3.gz":
                continue
            dest = settings.data_dir / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.replace(path, dest)
            restored_files += 1
        return {"app_version": manifest.get("app_version"), "created_at": manifest.get("created_at"),
                "rows": summary_rows, "files": restored_files,
                "secrets_restored": secrets_restored,
                "secrets_in_backup": secrets_blob is not None,
                "previous_database_kept_as": kept.name if kept else None}
    finally:
        shutil.rmtree(stage, ignore_errors=True)


# ---------------------------------------------------------------- share target + manager
BACKUP_INTERVALS = [0, 360, 720, 1440, 10080]  # minutes; 0 = manual uploads only


def load_target(conn, box: SecretBox):
    """Returns (SmbTarget, row) or None."""
    from .smb import SmbTarget

    row = conn.execute("SELECT * FROM backup_target WHERE id=1").fetchone()
    if row is None:
        return None
    try:
        password = box.decrypt(row["password_enc"])
    except ValueError:
        return None
    return SmbTarget(host=row["host"], share=row["share"], folder=row["folder"] or "",
                     username=row["username"], password=password, domain=row["domain"],
                     port=row["port"]), row


def target_status(conn, box: SecretBox) -> dict[str, Any]:
    row = conn.execute("SELECT * FROM backup_target WHERE id=1").fetchone()
    out: dict[str, Any] = {"configured": row is not None, "interval_options": BACKUP_INTERVALS}
    if row is None:
        return out
    nxt = None
    if row["interval_minutes"] > 0:
        base = datetime.fromisoformat(row["last_run_at"]) if row["last_run_at"] else datetime.now(UTC)
        from datetime import timedelta
        nxt = (base + timedelta(minutes=row["interval_minutes"])).isoformat(timespec="seconds")
    out.update({
        "host": row["host"], "port": row["port"], "share": row["share"], "folder": row["folder"],
        "username": row["username"], "domain": row["domain"],
        "interval_minutes": row["interval_minutes"], "keep": row["keep"],
        "last_run_at": row["last_run_at"], "last_status": row["last_status"],
        "last_message": row["last_message"], "next_run_at": nxt,
    })
    return out


def save_target(conn, box: SecretBox, *, host: str, port: int, share: str, folder: str,
                username: str, domain: str | None, password: str, interval_minutes: int,
                keep: int) -> None:
    conn.execute(
        "INSERT INTO backup_target (id, host, port, share, folder, username, domain, password_enc, "
        "interval_minutes, keep) VALUES (1,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET "
        "host=excluded.host, port=excluded.port, share=excluded.share, folder=excluded.folder, "
        "username=excluded.username, domain=excluded.domain, password_enc=excluded.password_enc, "
        "interval_minutes=excluded.interval_minutes, keep=excluded.keep",
        (host, port, share, folder, username, domain, box.encrypt(password), interval_minutes, keep))
    conn.commit()


def _record_run(conn, ok: bool, message: str) -> None:
    conn.execute("UPDATE backup_target SET last_run_at=?, last_status=?, last_message=? WHERE id=1",
                 (datetime.now(UTC).isoformat(timespec="seconds"), "ok" if ok else "error", message))
    conn.commit()


class BackupManager:
    """Creates backups (local, then to the share if one is set) and runs the schedule."""

    def __init__(self, settings: Settings, box: SecretBox) -> None:
        import threading
        self.settings, self.box = settings, box
        self.lock = threading.Lock()
        self.error: str | None = None
        self.last_ok: str | None = None
        self._threading = threading

    def start_background(self, passphrase: str | None = None) -> bool:
        if not self.lock.acquire(blocking=False):
            return False
        self._threading.Thread(target=self._guarded, args=(passphrase,), daemon=True,
                               name="backup").start()
        return True

    def _guarded(self, passphrase: str | None) -> None:
        try:
            self.run(passphrase)
        finally:
            self.lock.release()

    def run(self, passphrase: str | None = None) -> Path | None:
        """Caller must hold self.lock. Never raises; problems go to self.error."""
        from . import smb
        try:
            path = create_backup(self.settings, self.box, passphrase=passphrase or None)
        except Exception as exc:
            self.error = f"Backup failed: {type(exc).__name__}: {exc}"
            return None
        self.error = None
        self.last_ok = datetime.now(UTC).isoformat(timespec="seconds")
        conn = db.connect(self.settings.db_path)
        try:
            loaded = load_target(conn, self.box)
            if loaded is None:
                return path
            target, row = loaded
            try:
                size = smb.upload(target, path)
                removed = smb.prune_remote(target, row["keep"])
                _record_run(conn, True, f"Uploaded {size / 1e6:.1f} MB"
                            + (f"; removed {removed} old" if removed else ""))
            except smb.SmbError as exc:
                _record_run(conn, False, str(exc))
                self.error = f"Saved locally, but the share upload failed: {exc}"
        finally:
            conn.close()
        return path

    def maybe_run_scheduled(self) -> bool:
        conn = db.connect(self.settings.db_path)
        try:
            row = conn.execute("SELECT interval_minutes, last_run_at FROM backup_target WHERE id=1"
                               ).fetchone()
        finally:
            conn.close()
        if row is None or row["interval_minutes"] <= 0:
            return False
        from datetime import timedelta
        if row["last_run_at"]:
            due = datetime.now(UTC) >= datetime.fromisoformat(row["last_run_at"]) + timedelta(
                minutes=row["interval_minutes"])
            if not due:
                return False
        if not self.lock.acquire(blocking=False):
            return False
        try:
            self.run(None)  # scheduled backups never contain the Garmin key
        finally:
            self.lock.release()
        return True
