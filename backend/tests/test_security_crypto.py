import os
import stat

import pytest

from app import security
from app.crypto import SecretBox


def test_password_roundtrip():
    h = security.hash_password("correct horse battery")
    assert "correct" not in h
    assert security.verify_password("correct horse battery", h)
    assert not security.verify_password("wrong password!!", h)
    assert not security.verify_password("x", "garbage")


def test_secretbox_generates_and_reuses_key(tmp_path):
    box = SecretBox.load(tmp_path / "secrets", None)
    token = box.encrypt("hello")
    assert b"hello" not in token
    again = SecretBox.load(tmp_path / "secrets", None)
    assert again.decrypt(token) == "hello"
    mode = stat.S_IMODE(os.stat(tmp_path / "secrets" / "master.key").st_mode)
    assert mode == 0o600


def test_secretbox_app_secret_overrides_and_writes_no_file(tmp_path):
    box = SecretBox.load(tmp_path / "secrets", "my-deploy-secret")
    assert not (tmp_path / "secrets" / "master.key").exists()
    assert SecretBox.load(tmp_path / "x", "my-deploy-secret").decrypt(box.encrypt("a")) == "a"
    with pytest.raises(ValueError):
        SecretBox.load(tmp_path / "x", "different").decrypt(box.encrypt("a"))
