"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PORT = 26219  # marathon: 26.219 miles
DEFAULT_GARMIN_BASE_URL = "https://personal.connectapi.garmin.com"


def _flag(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("/data")
    static_dir: Path | None = None
    port: int = DEFAULT_PORT
    garmin_base_url: str = DEFAULT_GARMIN_BASE_URL
    secure_cookies: bool = False
    app_secret: str | None = None
    sync_interval_hours: float = 6.0  # 0 disables the background schedule
    backfill_days: int = 90
    session_days: int = 30
    request_delay_s: float = 0.25  # politeness delay between Garmin downloads

    @property
    def db_path(self) -> Path:
        return self.data_dir / "db" / "coach.sqlite3"

    @property
    def secrets_dir(self) -> Path:
        return self.data_dir / "secrets"

    @property
    def activities_dir(self) -> Path:
        return self.data_dir / "activities"

    @classmethod
    def from_env(cls) -> Settings:
        secret = os.environ.get("AEC_APP_SECRET")
        secret_file = os.environ.get("AEC_APP_SECRET_FILE")
        if not secret and secret_file:
            secret = Path(secret_file).read_text(encoding="utf-8").strip()
        static = os.environ.get("AEC_STATIC_DIR")
        return cls(
            data_dir=Path(os.environ.get("AEC_DATA_DIR", "/data")),
            static_dir=Path(static) if static else None,
            port=int(os.environ.get("PORT", DEFAULT_PORT)),
            garmin_base_url=os.environ.get("AEC_GARMIN_BASE_URL", DEFAULT_GARMIN_BASE_URL),
            secure_cookies=_flag("AEC_SECURE_COOKIES", False),
            app_secret=secret or None,
            sync_interval_hours=float(os.environ.get("AEC_SYNC_INTERVAL_HOURS", 6)),
            backfill_days=int(os.environ.get("AEC_BACKFILL_DAYS", 90)),
        )
