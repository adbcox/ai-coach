"""Backup upload to an SMB/CIFS share (a NAS, a Windows share, Samba).

Uses the pure-Python smbprotocol client from inside the container, so the host
needs no mount and the container no extra privileges. Files are written under
their final name, size-verified, and deleted again if anything goes wrong.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

NAME_RE = re.compile(r"^ai-endurance-coach-backup-\d{8}-\d{6}\.tar$")
_HOST_RE = re.compile(r"^[A-Za-z0-9._:-]+$")
_SHARE_RE = re.compile(r"^[^\\/:*?\"<>|]+$")
TEST_FILE = ".aec-write-test"


class SmbError(Exception):
    """A problem with the share, with a message safe to show to the user."""


@dataclass
class SmbTarget:
    host: str
    share: str
    folder: str
    username: str
    password: str
    domain: str | None = None
    port: int = 445


def validate(t: SmbTarget) -> None:
    if not t.host or not _HOST_RE.match(t.host):
        raise SmbError("Host must be a name or IP address (no slashes).")
    if not 1 <= t.port <= 65535:
        raise SmbError("Port must be between 1 and 65535.")
    if not t.share or not _SHARE_RE.match(t.share):
        raise SmbError("Share name is missing or contains invalid characters.")
    parts = [p for p in re.split(r"[\\/]+", t.folder or "") if p]
    if any(p in (".", "..") or not _SHARE_RE.match(p) for p in parts):
        raise SmbError("Folder may not contain '..' or special characters.")
    if not t.username:
        raise SmbError("Username is required.")


def _folder(t: SmbTarget) -> str:
    return "\\".join(p for p in re.split(r"[\\/]+", t.folder or "") if p)


def _base(t: SmbTarget) -> str:
    folder = _folder(t)
    return rf"\\{t.host}\{t.share}" + (f"\\{folder}" if folder else "")


def _client(t: SmbTarget):
    import smbclient  # imported lazily: only needed when a share is configured

    validate(t)
    user = f"{t.domain}\\{t.username}" if t.domain else t.username
    try:
        smbclient.register_session(t.host, username=user, password=t.password,
                                   port=t.port, connection_timeout=15)
    except Exception as exc:
        raise _friendly(exc, t) from exc
    return smbclient


def _friendly(exc: Exception, t: SmbTarget) -> SmbError:
    if isinstance(exc, SmbError):
        return exc
    text = f"{type(exc).__name__} {exc}"
    low = text.lower()
    if "logon" in low or "access_denied" in low or "unauthorized" in low or "password" in low:
        return SmbError("The share rejected the username or password (or the account lacks access).")
    if "bad_network_name" in low or "no_such_share" in low:
        return SmbError(f"Share '{t.share}' was not found on {t.host}.")
    if "object_path_not_found" in low or "no_such_file" in low or "name_not_found" in low:
        return SmbError("The folder was not found and could not be created.")
    if "disk_full" in low or "quota" in low or "no space" in low:
        return SmbError("The share is out of space.")
    if any(k in low for k in ("connect", "timed out", "timeout", "refused", "unreachable",
                              "name or service", "resolve", "reset")):
        return SmbError(f"Could not connect to {t.host}:{t.port}. Check the address and that SMB is reachable.")
    return SmbError(f"SMB error: {type(exc).__name__}: {str(exc)[:160]}")


def check_connection(t: SmbTarget) -> None:
    """Sign in, create the folder if needed, and prove it is writable."""
    c = _client(t)
    base = _base(t)
    try:
        c.makedirs(base, exist_ok=True, port=t.port)
        probe = f"{base}\\{TEST_FILE}"
        with c.open_file(probe, mode="wb", port=t.port) as handle:
            handle.write(b"ok")
        c.remove(probe, port=t.port)
    except Exception as exc:
        raise _friendly(exc, t) from exc


def upload(t: SmbTarget, local: Path) -> int:
    if not NAME_RE.match(local.name):
        raise SmbError("Refusing to upload a file that is not an app backup.")
    c = _client(t)
    base = _base(t)
    dest = f"{base}\\{local.name}"
    size = local.stat().st_size
    try:
        c.makedirs(base, exist_ok=True, port=t.port)
        with open(local, "rb") as src, c.open_file(dest, mode="wb", port=t.port) as out:
            shutil.copyfileobj(src, out, length=4 * 1024 * 1024)
        remote = c.stat(dest, port=t.port).st_size
        if remote != size:
            raise SmbError(f"Upload incomplete ({remote} of {size} bytes).")
    except Exception as exc:
        try:
            c.remove(dest, port=t.port)  # never leave a partial backup behind
        except Exception:
            pass
        raise _friendly(exc, t) from exc
    return size


def list_remote(t: SmbTarget) -> list[dict]:
    c = _client(t)
    base = _base(t)
    try:
        out = []
        for name in c.listdir(base, port=t.port):
            if NAME_RE.match(name):
                st = c.stat(f"{base}\\{name}", port=t.port)
                out.append({"name": name, "size": st.st_size,
                            "created_at": datetime.fromtimestamp(st.st_mtime, UTC).isoformat(
                                timespec="seconds")})
        return sorted(out, key=lambda e: e["name"], reverse=True)
    except Exception as exc:
        raise _friendly(exc, t) from exc


def prune_remote(t: SmbTarget, keep: int) -> int:
    """Delete the oldest backups beyond `keep` (only files with our exact name pattern)."""
    c = _client(t)
    base = _base(t)
    old = list_remote(t)[max(1, keep):]
    try:
        for entry in old:
            c.remove(f"{base}\\{entry['name']}", port=t.port)
    except Exception as exc:
        raise _friendly(exc, t) from exc
    return len(old)


def local_name(path: Path) -> str:
    return path.name
