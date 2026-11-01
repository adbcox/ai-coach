"""Garmin wellness data (sleep, HRV, Body Battery, stress, HR, SpO2, ...).

Collected as raw JSON so nothing is lost; walks backwards from today until the
data runs out. Past windows are fetched once; the most recent days are always
refreshed. A 404 on one data type skips that type rather than failing the sync.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from .config import Settings
from .garmin.client import GarminClient, GarminError

SOURCE = "garmin"
CHUNK_DAYS = 28
EMPTY_CHUNKS_STOP = 8   # consecutive empty 28-day windows => end of history
EMPTY_DAYS_STOP = 45    # consecutive empty days => end of history
RECENT_CHUNKS = 2       # always refresh the newest windows
RECENT_DAYS = 3


@dataclass(frozen=True)
class RangeKind:
    name: str
    path: str                     # may contain {start} / {end}
    query: bool = False           # True: startDate/endDate as query params
    extra: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class DayKind:
    name: str
    path: str                     # may contain {date}
    query_date: bool = False      # True: ?date=


RANGE_KINDS = [
    RangeKind("daily_summaries", "/usersummary-service/v2/dailysummaries", query=True),
    RangeKind("sleep_summaries", "/sleep-service/sleep/dailySleepSummariesByDate", query=True),
    RangeKind("hrv_summaries", "/hrv-service/hrv/daily/{start}/{end}"),
    RangeKind("body_battery", "/wellness-service/wellness/bodyBattery/reports/daily", query=True),
    RangeKind("steps", "/usersummary-service/stats/steps/daily/{start}/{end}"),
    RangeKind("hydration", "/usersummary-service/stats/hydration/daily/{start}/{end}"),
    RangeKind("weight", "/weight-service/weight/range/{start}/{end}", extra=(("includeAll", "true"),)),
]
DAY_KINDS = [
    DayKind("sleep", "/sleep-service/sleep/dailySleep", query_date=True),
    DayKind("hrv", "/hrv-service/hrv/{date}"),
    DayKind("heart_rate", "/wellness-service/wellness/dailyHeartRate", query_date=True),
    DayKind("spo2", "/wellness-service/wellness/daily/spo2acclimation/{date}"),
]

Progress = Callable[[str], None]


def is_empty(value: Any) -> bool:
    if value is None or value == "" or value == [] or value == {}:
        return True
    if isinstance(value, list):
        return all(is_empty(v) for v in value)
    if isinstance(value, dict):
        return all(is_empty(v) for v in value.values())
    return False


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def get_state(conn, key: str) -> str | None:
    row = conn.execute("SELECT value FROM sync_state WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def set_state(conn, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO sync_state (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit()


def _stored(conn, kind: str, start: str, end: str):
    return conn.execute(
        "SELECT is_empty FROM wellness_raw WHERE source=? AND kind=? AND start_date=? "
        "AND end_date=?", (SOURCE, kind, start, end)).fetchone()


def _save(conn, kind: str, start: str, end: str, payload: Any) -> bool:
    empty = is_empty(payload)
    conn.execute(
        "INSERT OR REPLACE INTO wellness_raw (source, kind, start_date, end_date, fetched_at, "
        "is_empty, payload) VALUES (?,?,?,?,?,?,?)",
        (SOURCE, kind, start, end, _now(), 1 if empty else 0, json.dumps(payload)))
    return empty


def _chunk(index: int) -> tuple[date, date]:
    start = date.fromordinal(max(1, index * CHUNK_DAYS))
    return start, start + timedelta(days=CHUNK_DAYS - 1)


def _range_request(kind: RangeKind, start: date, end: date) -> tuple[str, dict[str, Any] | None]:
    s, e = start.isoformat(), end.isoformat()
    params: dict[str, Any] = dict(kind.extra)
    if kind.query:
        params.update({"startDate": s, "endDate": e})
        return kind.path, params
    return kind.path.format(start=s, end=e), params or None


def _day_request(kind: DayKind, day: date) -> tuple[str, dict[str, Any] | None]:
    if kind.query_date:
        return kind.path, {"date": day.isoformat()}
    return kind.path.format(date=day.isoformat()), None


class Walker:
    def __init__(self, conn, client: GarminClient, settings: Settings, progress: Progress,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self.conn, self.client, self.settings = conn, client, settings
        self.progress, self.sleep = progress, sleep
        self.fetched = 0
        self.notes: list[str] = []

    def _fetch(self, path: str, params):
        payload = self.client.get_json(path, params)
        self.fetched += 1
        if self.settings.request_delay_s:
            self.sleep(self.settings.request_delay_s)
        return payload

    def range_kind(self, kind: RangeKind, floor: date, full: bool) -> None:
        state_key = f"wellness_{kind.name}_done"
        done = get_state(self.conn, state_key) == "1" and not full
        newest = date.today().toordinal() // CHUNK_DAYS
        oldest = floor.toordinal() // CHUNK_DAYS
        empties = 0
        reached_end = False
        for age, index in enumerate(range(newest, oldest - 1, -1)):
            if done and age >= RECENT_CHUNKS:
                return
            start, end = _chunk(index)
            have = _stored(self.conn, kind.name, start.isoformat(), end.isoformat())
            if have is not None and age >= RECENT_CHUNKS:
                empties = empties + 1 if have["is_empty"] else 0
            else:
                path, params = _range_request(kind, start, end)
                try:
                    payload = self._fetch(path, params)
                except GarminError as exc:
                    if exc.status == 404:
                        self.notes.append(f"{kind.name}: not available (404)")
                        return
                    raise
                empties = empties + 1 if _save(self.conn, kind.name, start.isoformat(),
                                               end.isoformat(), payload) else 0
                self.conn.commit()
                if self.fetched % 10 == 0:
                    self.progress(f"Health data: {kind.name} back to {start}")
            if empties >= EMPTY_CHUNKS_STOP:
                reached_end = True
                break
        if reached_end or index == oldest:
            set_state(self.conn, state_key, "1")

    def day_kind(self, kind: DayKind, floor: date, full: bool) -> None:
        state_key = f"wellness_{kind.name}_done"
        done = get_state(self.conn, state_key) == "1" and not full
        today = date.today()
        empties = 0
        day = today
        age = 0
        while day >= floor:
            if done and age >= RECENT_DAYS:
                return
            iso = day.isoformat()
            have = _stored(self.conn, kind.name, iso, iso)
            if have is not None and age >= RECENT_DAYS:
                empties = empties + 1 if have["is_empty"] else 0
            else:
                path, params = _day_request(kind, day)
                try:
                    payload = self._fetch(path, params)
                except GarminError as exc:
                    if exc.status == 404:
                        # 404 can mean "no data that day" or "no such endpoint"; a day
                        # of nothing is stored as empty so it is not asked again.
                        payload = None
                    else:
                        raise
                empties = empties + 1 if _save(self.conn, kind.name, iso, iso, payload) else 0
                self.conn.commit()
                if self.fetched % 25 == 0:
                    self.progress(f"Health data: {kind.name} back to {iso}")
            if empties >= EMPTY_DAYS_STOP:
                set_state(self.conn, state_key, "1")
                return
            day -= timedelta(days=1)
            age += 1
        set_state(self.conn, state_key, "1")


def sync_wellness(conn, client: GarminClient, settings: Settings, *, full: bool,
                  progress: Progress, floor: date) -> list[str]:
    """Returns human-readable notes (kinds that were unavailable, etc.)."""
    walker = Walker(conn, client, settings, progress)
    for rk in RANGE_KINDS:
        walker.range_kind(rk, floor, full)
    for dk in DAY_KINDS:
        walker.day_kind(dk, floor, full)
    return walker.notes
