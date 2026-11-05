"""Conservative Garmin backfill throttle (dispatch-05 P1).

Why this exists
    Garmin does not publish Personal API rate limits. Community reports from
    the unofficial password-login library show 429s and 48-hour account blocks
    on bursty usage. The base 0.25s politeness delay + 4x local retry is fine
    for 90-day syncs but far too aggressive for 10-year backfills. This
    module adds a serious throttle around backfill specifically; non-backfill
    syncs keep the base behaviour.

What it enforces (all configurable via Settings / env)
    - Minimum spacing between backfill requests: ``backfill_delay_s`` (3s).
    - Daily request cap per UTC day: ``backfill_daily_cap`` (2000).
    - On any 429 or 5xx burst: stop immediately, write a pause marker, and
      refuse further backfill requests for ``backfill_pause_hours`` (24h).
    - On resume after a pause, halve the request rate (double the delay)
      when ``backfill_rate_halving`` is true.

State is persisted in ``sync_state`` so a restart does not reset the budget:
    throttle.day                   -> 'YYYY-MM-DD'  (UTC day the counter is for)
    throttle.day_count             -> int           (requests made today)
    throttle.hour                  -> 'YYYY-MM-DDTHH' (UTC hour)
    throttle.hour_count            -> int           (requests this hour)
    throttle.last_request_ts       -> float         (unix seconds)
    throttle.pause_until_ts        -> float         (unix seconds; 0 if none)
    throttle.current_delay_s       -> float         (effective min spacing)
    throttle.last_pause_reason     -> str           (e.g. 'http 429')
    throttle.last_pause_at         -> ISO8601
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

from .config import Settings
from .wellness import get_state, set_state


class ThrottlePaused(Exception):
    """Raised when a backfill call is attempted while the throttle is paused."""


class OutsideWindow(ThrottlePaused):
    """Raised when a backfill call is attempted outside the nightly window."""


def _parse_hhmm(value: str) -> dtime:
    hh, mm = value.split(":", 1)
    return dtime(int(hh), int(mm))


def window_is_open(settings: Settings, now: datetime | None = None) -> bool:
    tz = ZoneInfo(settings.backfill_window_tz)
    local = (now or datetime.now(UTC)).astimezone(tz)
    start = _parse_hhmm(settings.backfill_window_start)
    end = _parse_hhmm(settings.backfill_window_end)
    if start == end:
        # Sentinel for "no window" (always open) — used in tests and for
        # operators who want 24/7 backfill.
        return True
    t = local.time()
    # Window wraps midnight if end < start (e.g. 23:00 -> 06:00).
    if end < start:
        return t >= start or t < end
    return start <= t < end


def next_window_open(settings: Settings, now: datetime | None = None) -> datetime:
    """UTC datetime of the next moment the window opens (or "now" if already open)."""
    tz = ZoneInfo(settings.backfill_window_tz)
    local = (now or datetime.now(UTC)).astimezone(tz)
    start = _parse_hhmm(settings.backfill_window_start)
    if window_is_open(settings, now):
        return (now or datetime.now(UTC)).astimezone(UTC)
    candidate = local.replace(hour=start.hour, minute=start.minute, second=0, microsecond=0)
    if candidate <= local:
        candidate = candidate + timedelta(days=1)
    return candidate.astimezone(UTC)


@dataclass
class ThrottleSnapshot:
    day: str
    day_count: int
    hour: str
    hour_count: int
    last_request_ts: float
    pause_until_ts: float
    current_delay_s: float
    daily_cap: int


def _utc_day() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _utc_hour() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H")


class GarminThrottle:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._day = ""
        self._day_count = 0
        self._hour = ""
        self._hour_count = 0
        self._last_request_ts = 0.0
        self._pause_until_ts = 0.0
        self._current_delay_s = float(settings.backfill_delay_s)

    # ----- persistence -----

    def load(self, conn) -> None:
        self._day = get_state(conn, "throttle.day") or ""
        self._day_count = int(get_state(conn, "throttle.day_count") or 0)
        self._hour = get_state(conn, "throttle.hour") or ""
        self._hour_count = int(get_state(conn, "throttle.hour_count") or 0)
        try:
            self._last_request_ts = float(get_state(conn, "throttle.last_request_ts") or 0.0)
        except ValueError:
            self._last_request_ts = 0.0
        try:
            self._pause_until_ts = float(get_state(conn, "throttle.pause_until_ts") or 0.0)
        except ValueError:
            self._pause_until_ts = 0.0
        try:
            stored = float(
                get_state(conn, "throttle.current_delay_s") or self.settings.backfill_delay_s,
            )
        except ValueError:
            stored = float(self.settings.backfill_delay_s)
        # Effective delay is always at least the env floor. A burst-halved value
        # (bigger than env) stays; a stale carry-over below env is lifted so
        # an operator bumping AEC_BACKFILL_DELAY_S takes effect at restart.
        self._current_delay_s = max(float(self.settings.backfill_delay_s), stored)

    def _persist(self, conn) -> None:
        set_state(conn, "throttle.day", self._day)
        set_state(conn, "throttle.day_count", str(self._day_count))
        set_state(conn, "throttle.hour", self._hour)
        set_state(conn, "throttle.hour_count", str(self._hour_count))
        set_state(conn, "throttle.last_request_ts", f"{self._last_request_ts:.3f}")
        set_state(conn, "throttle.pause_until_ts", f"{self._pause_until_ts:.3f}")
        set_state(conn, "throttle.current_delay_s", f"{self._current_delay_s:.3f}")

    # ----- lifecycle -----

    def before_request(self, conn, *, kind: str = "search") -> None:
        """Called before each backfill request. Blocks (sleeps) for the spacing
        delay, enforces the daily cap, enforces the nightly window, and raises
        ``ThrottlePaused`` (or its ``OutsideWindow`` subclass) if traffic is
        currently forbidden. ``kind`` is for logging only.
        """
        now = time.time()
        if not window_is_open(self.settings):
            nxt = next_window_open(self.settings).strftime("%Y-%m-%dT%H:%MZ")
            raise OutsideWindow(
                f"Garmin backfill window closed; resumes at {nxt} "
                f"({self.settings.backfill_window_start}-{self.settings.backfill_window_end} "
                f"{self.settings.backfill_window_tz}).",
            )
        if self._pause_until_ts > now:
            wait = self._pause_until_ts - now
            reason = get_state(conn, "throttle.last_pause_reason") or "unknown"
            raise ThrottlePaused(
                f"Garmin throttle paused for another {wait / 3600:.1f}h (reason: {reason}).",
            )
        # roll windows
        day = _utc_day()
        hour = _utc_hour()
        if day != self._day:
            self._day = day
            self._day_count = 0
        if hour != self._hour:
            self._hour = hour
            self._hour_count = 0
        # daily cap
        if self._day_count >= self.settings.backfill_daily_cap:
            # not a ban-worthy pause, just end the run for today
            self._pause_until_ts = self._midnight_utc_ts()
            set_state(conn, "throttle.last_pause_reason", "daily cap reached")
            set_state(conn, "throttle.last_pause_at", datetime.now(UTC).isoformat(timespec="seconds"))
            self._persist(conn)
            raise ThrottlePaused(
                f"Garmin throttle: daily cap {self.settings.backfill_daily_cap} reached; "
                f"resumes after UTC midnight.",
            )
        # spacing
        gap = now - self._last_request_ts
        if gap < self._current_delay_s:
            time.sleep(self._current_delay_s - gap)
        self._last_request_ts = time.time()
        self._day_count += 1
        self._hour_count += 1
        self._persist(conn)

    def hit_burst(self, conn, status: int) -> None:
        """Called when a 429 or 5xx is observed during backfill. Pause 24h,
        halve the rate, persist. Never retries in a loop here."""
        now = time.time()
        self._pause_until_ts = now + self.settings.backfill_pause_hours * 3600
        if self.settings.backfill_rate_halving:
            self._current_delay_s = max(self._current_delay_s * 2.0, float(self.settings.backfill_delay_s))
        set_state(conn, "throttle.last_pause_reason", f"http {status}")
        set_state(conn, "throttle.last_pause_at", datetime.now(UTC).isoformat(timespec="seconds"))
        self._persist(conn)

    def snapshot(self, conn) -> ThrottleSnapshot:
        self.load(conn)
        return ThrottleSnapshot(
            day=self._day,
            day_count=self._day_count,
            hour=self._hour,
            hour_count=self._hour_count,
            last_request_ts=self._last_request_ts,
            pause_until_ts=self._pause_until_ts,
            current_delay_s=self._current_delay_s,
            daily_cap=self.settings.backfill_daily_cap,
        )

    @staticmethod
    def _midnight_utc_ts() -> float:
        now = datetime.now(UTC)
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return tomorrow.timestamp() + 86400
