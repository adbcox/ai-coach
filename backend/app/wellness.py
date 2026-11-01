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
HISTORY_FLOOR = date(2010, 1, 1)  # never look further back than this
EMPTY_CHUNKS_STOP = 12  # consecutive empty 28-day windows (~1 year) => end of history
EMPTY_DAYS_STOP = 120   # consecutive empty days (~4 months) => end of history


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


def _dig(obj: Any, *keys: str) -> Any:
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _any(items: Any, pred: Callable[[dict], bool]) -> bool:
    return isinstance(items, list) and any(pred(i) for i in items if isinstance(i, dict))


# Garmin returns well-formed objects full of nulls for days without data, so "empty"
# is decided per data type (shapes seen in a real account).
_HAS_DATA: dict[str, Callable[[Any], bool]] = {
    "sleep": lambda p: bool(_dig(p, "sleepTimeSeconds")),
    "hrv": lambda p: _dig(p, "hrvSummary", "lastNightAvg") is not None or bool(_dig(p, "hrvReadings")),
    "heart_rate": lambda p: _dig(p, "restingHeartRate") is not None or bool(_dig(p, "heartRateValues")),
    "daily_summaries": lambda p: _any(
        _dig(p, "data"),
        lambda d: _dig(d, "movement", "steps", "value") is not None
        or _dig(d, "heartRate", "restingValue") is not None),
    "body_battery": lambda p: _any(
        p, lambda d: d.get("charged") is not None or bool(d.get("bodyBatteryValueDescriptorDTOList"))),
    "sleep_summaries": lambda p: _any(p, lambda d: bool(d.get("sleepTimeSeconds"))),
    "hrv_summaries": lambda p: _any(
        _dig(p, "hrvSummaries"),
        lambda d: d.get("lastNightAvg") is not None or d.get("weeklyAvg") is not None),
    "steps": lambda p: _any(p, lambda d: d.get("totalSteps") is not None),
    "weight": lambda p: bool(_dig(p, "dailyWeightSummaries")),
}


def has_data(kind: str, payload: Any) -> bool:
    check = _HAS_DATA.get(kind)
    if check is not None:
        try:
            return bool(check(payload))
        except (AttributeError, TypeError):
            pass
    return not is_empty(payload)


def reclassify(conn) -> None:
    """One-off: recompute the empty flag of rows stored by earlier versions."""
    if get_state(conn, "wellness_reclassified_v2") == "1":
        return
    for row in conn.execute("SELECT kind, start_date, end_date, payload FROM wellness_raw").fetchall():
        try:
            empty = 0 if has_data(row["kind"], json.loads(row["payload"])) else 1
        except ValueError:
            continue
        conn.execute("UPDATE wellness_raw SET is_empty=? WHERE source=? AND kind=? AND start_date=? "
                     "AND end_date=?", (empty, SOURCE, row["kind"], row["start_date"], row["end_date"]))
    conn.commit()
    set_state(conn, "wellness_reclassified_v2", "1")


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


def newest_nonempty(conn, kind: str) -> date | None:
    row = conn.execute(
        "SELECT MAX(end_date) AS d FROM wellness_raw WHERE source=? AND kind=? AND is_empty=0",
        (SOURCE, kind)).fetchone()
    return date.fromisoformat(row["d"]) if row and row["d"] else None


def refresh_from(conn, kind: str, lookback_days: int) -> date:
    """Start of the window that is always re-fetched: newest stored data minus lookback."""
    newest = newest_nonempty(conn, kind) or date.today()
    return min(newest, date.today()) - timedelta(days=lookback_days)


def _stored(conn, kind: str, start: str, end: str):
    return conn.execute(
        "SELECT is_empty FROM wellness_raw WHERE source=? AND kind=? AND start_date=? "
        "AND end_date=?", (SOURCE, kind, start, end)).fetchone()


def _save(conn, kind: str, start: str, end: str, payload: Any) -> bool:
    empty = not has_data(kind, payload)
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

    def range_kind(self, kind: RangeKind, floor: date, full: bool, lookback: int) -> None:
        state_key = f"wellness_v2_{kind.name}_done"
        done = get_state(self.conn, state_key) == "1" and not full
        since = refresh_from(self.conn, kind.name, lookback)
        newest = date.today().toordinal() // CHUNK_DAYS
        oldest = floor.toordinal() // CHUNK_DAYS
        empties = 0
        reached_end = False
        for index in range(newest, oldest - 1, -1):
            start, end = _chunk(index)
            refresh = end >= since
            if done and not refresh:
                return
            have = _stored(self.conn, kind.name, start.isoformat(), end.isoformat())
            if have is not None and not refresh:
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

    def day_kind(self, kind: DayKind, floor: date, full: bool, lookback: int) -> None:
        state_key = f"wellness_v2_{kind.name}_done"
        done = get_state(self.conn, state_key) == "1" and not full
        since = refresh_from(self.conn, kind.name, lookback)
        empties = 0
        day = date.today()
        while day >= floor:
            refresh = day >= since
            if done and not refresh:
                return
            iso = day.isoformat()
            have = _stored(self.conn, kind.name, iso, iso)
            if have is not None and not refresh:
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
        set_state(self.conn, state_key, "1")


def sync_snapshots(conn, client: GarminClient, settings: Settings, notes: list[str]) -> None:
    """Things without a history (current settings such as heart-rate zones), stored raw."""
    today = date.today().isoformat()
    try:
        payload = client.get_json("/biometric-service/heartRateZones/v2")
    except GarminError as exc:
        if exc.status != 404:
            raise
        notes.append("heart_rate_zones: not available (404)")
        return
    _save(conn, "heart_rate_zones", today, today, payload)
    conn.commit()


def sync_wellness(conn, client: GarminClient, settings: Settings, *, full: bool,
                  progress: Progress, floor: date, lookback: int) -> list[str]:
    """Returns human-readable notes (kinds that were unavailable, etc.)."""
    reclassify(conn)
    floor = max(floor, HISTORY_FLOOR)
    walker = Walker(conn, client, settings, progress)
    for rk in RANGE_KINDS:
        walker.range_kind(rk, floor, full, lookback)
    for dk in DAY_KINDS:
        walker.day_kind(dk, floor, full, lookback)
    sync_snapshots(conn, client, settings, walker.notes)
    return walker.notes
