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
    # Nightly backfill window (local time, IANA zone). All Garmin traffic
    # (search + download + wellness) is gated to this window.
    backfill_window_start: str = "23:00"     # HH:MM, inclusive
    backfill_window_end: str = "06:00"       # HH:MM, exclusive (next day if < start)
    backfill_window_tz: str = "America/New_York"
    # P2b life feeds. Each secret is mounted as a runtime secret FILE by the
    # Mini-side launcher (same pattern as the Garmin key); the container never
    # sees Infisical credentials. All three are optional — a missing file just
    # disables the corresponding feed with an audit-log line.
    calendar_ics_url_file: Path | None = None
    hass_token_file: Path | None = None
    hass_base_url: str = "http://ha.internal:8123"
    # Open-Meteo archive is key-free; we just need Adrian's home coordinates
    # to resolve "weather on this day" for daily rollups.
    home_latitude: float | None = None
    home_longitude: float | None = None

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
            backfill_window_start=os.environ.get("AEC_BACKFILL_WINDOW_START", "23:00"),
            backfill_window_end=os.environ.get("AEC_BACKFILL_WINDOW_END", "06:00"),
            backfill_window_tz=os.environ.get("AEC_BACKFILL_WINDOW_TZ", "America/New_York"),
            calendar_ics_url_file=Path(os.environ["AEC_CALENDAR_ICS_URL_FILE"])
                if os.environ.get("AEC_CALENDAR_ICS_URL_FILE") else None,
            hass_token_file=Path(os.environ["AEC_HASS_TOKEN_FILE"])
                if os.environ.get("AEC_HASS_TOKEN_FILE") else None,
            hass_base_url=os.environ.get("AEC_HASS_BASE_URL", "http://ha.internal:8123"),
            home_latitude=float(os.environ["AEC_HOME_LATITUDE"])
                if os.environ.get("AEC_HOME_LATITUDE") else None,
            home_longitude=float(os.environ["AEC_HOME_LONGITUDE"])
                if os.environ.get("AEC_HOME_LONGITUDE") else None,
        )
