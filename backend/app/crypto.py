"""Encryption of stored provider secrets (Fernet).

The master key is generated on first run and stored in the secrets directory,
separate from the database (owner-only permissions). Setting AEC_APP_SECRET
(or AEC_APP_SECRET_FILE) overrides it, so on a cloud host the master key never
has to live on the data volume.
"""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class SecretBox:
    def __init__(self, key: bytes) -> None:
        self._fernet = Fernet(key)

    @classmethod
    def load(cls, secrets_dir: Path, app_secret: str | None) -> SecretBox:
        if app_secret:
            derived = base64.urlsafe_b64encode(hashlib.sha256(app_secret.encode()).digest())
            return cls(derived)
        secrets_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(secrets_dir, 0o700)
        path = secrets_dir / "master.key"
        if path.exists():
            return cls(path.read_bytes().strip())
        key = Fernet.generate_key()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(key)
        return cls(key)

    def encrypt(self, value: str) -> bytes:
        return self._fernet.encrypt(value.encode())

    def decrypt(self, token: bytes) -> str:
        try:
            return self._fernet.decrypt(token).decode()
        except InvalidToken as exc:
            raise ValueError(
                "Stored secret cannot be decrypted (master key changed?). Re-enter the key."
            ) from exc
