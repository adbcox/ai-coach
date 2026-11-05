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
    # P1: key is injected as a runtime secret file by the Mini-side launcher
    # (native Infisical CLI only); never pasted in the UI, never in the DB.
    garmin_api_key_file: Path | None = None
    # Backfill throttle (dispatch-05): conservative defaults; override via env.
    backfill_delay_s: float = 3.0            # min seconds between backfill requests
    backfill_daily_cap: int = 2000           # max Garmin requests per UTC day
    backfill_pause_hours: float = 24.0       # hours to pause after a 429/5xx burst
    backfill_rate_halving: bool = True       # halve rate on resume after pause

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
        key_file = os.environ.get("AEC_GARMIN_API_KEY_FILE")
        return cls(
            data_dir=Path(os.environ.get("AEC_DATA_DIR", "/data")),
            static_dir=Path(static) if static else None,
            port=int(os.environ.get("PORT", DEFAULT_PORT)),
            garmin_base_url=os.environ.get("AEC_GARMIN_BASE_URL", DEFAULT_GARMIN_BASE_URL),
            secure_cookies=_flag("AEC_SECURE_COOKIES", False),
            app_secret=secret or None,
            sync_interval_hours=float(os.environ.get("AEC_SYNC_INTERVAL_HOURS", 6)),
            backfill_days=int(os.environ.get("AEC_BACKFILL_DAYS", 90)),
            garmin_api_key_file=Path(key_file) if key_file else None,
            backfill_delay_s=float(os.environ.get("AEC_BACKFILL_DELAY_S", 3.0)),
            backfill_daily_cap=int(os.environ.get("AEC_BACKFILL_DAILY_CAP", 2000)),
            backfill_pause_hours=float(os.environ.get("AEC_BACKFILL_PAUSE_HOURS", 24.0)),
            backfill_rate_halving=_flag("AEC_BACKFILL_RATE_HALVING", True),
        )
