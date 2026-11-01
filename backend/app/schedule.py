"""Per-source automatic sync schedule (stored in sync_state)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from .config import Settings
from .wellness import get_state, set_state

# minutes; 0 = off
INTERVAL_OPTIONS = [0, 60, 180, 360, 720, 1440]
MODES = ("quick", "background", "full")
LOOKBACK_DAYS = {"quick": 1, "background": 30, "full": 30}


def _key(source: str) -> str:
    return f"{source}_interval_minutes"


def get_interval(conn, source: str, settings: Settings) -> int:
    value = get_state(conn, _key(source))
    if value is not None:
        try:
            return int(value)
        except ValueError:
            pass
    return int(settings.sync_interval_hours * 60)  # default from env (6 h)


def set_interval(conn, source: str, minutes: int) -> None:
    if minutes != 0 and not 15 <= minutes <= 7 * 1440:
        raise ValueError("Interval must be off, or between 15 minutes and 7 days.")
    set_state(conn, _key(source), str(minutes))


def last_deep_run(conn, source: str) -> datetime | None:
    """Last background/full run; quick (home-page) syncs do not reset the timer."""
    row = conn.execute(
        "SELECT started_at FROM sync_runs WHERE provider=? AND mode IN ('background','full') "
        "ORDER BY id DESC LIMIT 1", (source,)).fetchone()
    return datetime.fromisoformat(row["started_at"]) if row else None


def next_run(conn, source: str, settings: Settings, now: datetime | None = None) -> datetime | None:
    interval = get_interval(conn, source, settings)
    if interval <= 0:
        return None
    last = last_deep_run(conn, source)
    now = now or datetime.now(UTC)
    return (last + timedelta(minutes=interval)) if last else now


def is_due(conn, source: str, settings: Settings, now: datetime | None = None) -> bool:
    nxt = next_run(conn, source, settings, now)
    return nxt is not None and (now or datetime.now(UTC)) >= nxt
