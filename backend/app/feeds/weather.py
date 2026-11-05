"""Open-Meteo ERA5 archive fetch (no API key). Fills `activity_weather`
(one row per activity, nearest hour at start_time) and `weather_day`
(one row per day).

Design notes:
  - We fetch one day at a time per outstanding activity so that a reset
    of `activity_weather` can be re-run idempotently.
  - If `settings.home_latitude/longitude` are None, the feed is disabled
    (returns without hitting the network). This lets the launcher gate the
    feed with env vars — no DB rows, no silent surprises.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import httpx

from ..config import Settings

_LOG = logging.getLogger("feeds.weather")

_BASE = "https://archive-api.open-meteo.com/v1/archive"
_HOURLY = ",".join([
    "temperature_2m", "apparent_temperature", "dew_point_2m",
    "relative_humidity_2m", "wind_speed_10m", "precipitation",
])
_DAILY = ",".join([
    "temperature_2m_min", "temperature_2m_max",
    "apparent_temperature_mean", "dew_point_2m_mean",
    "relative_humidity_2m_mean", "precipitation_sum",
])


@dataclass
class WeatherStats:
    activity_rows: int = 0
    day_rows: int = 0
    skipped: int = 0


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _parse_start(row: sqlite3.Row) -> datetime | None:
    try:
        return datetime.fromisoformat(row["start_time"])
    except (ValueError, TypeError):
        return None


def _nearest_hour_index(hour_series: list[str], target: datetime) -> int | None:
    """Find the hourly bucket closest to the target time (UTC)."""
    best_idx: int | None = None
    best_delta = None
    for i, iso in enumerate(hour_series):
        try:
            t = datetime.fromisoformat(iso).replace(tzinfo=UTC)
        except ValueError:
            continue
        delta = abs((t - target.astimezone(UTC)).total_seconds())
        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_idx = i
    return best_idx


def _get(url: str, params: dict[str, Any], client: httpx.Client | None = None) -> dict[str, Any] | None:
    try:
        if client is None:
            r = httpx.get(url, params=params, timeout=15)
        else:
            r = client.get(url, params=params, timeout=15)
        if r.status_code != 200:
            _LOG.warning("weather fetch %s: HTTP %s", url, r.status_code)
            return None
        return r.json()
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        _LOG.warning("weather fetch failed: %s", exc)
        return None


def backfill_pending(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    limit: int = 50,
    client: httpx.Client | None = None,
) -> WeatherStats:
    """Fetch weather for up to `limit` activities that don't yet have a row
    in `activity_weather`. Idempotent; call repeatedly."""
    stats = WeatherStats()
    if settings.home_latitude is None or settings.home_longitude is None:
        _LOG.info("weather disabled: AEC_HOME_LATITUDE/LONGITUDE unset")
        return stats
    rows = conn.execute(
        "SELECT a.id, a.start_time FROM activities a "
        "LEFT JOIN activity_weather w ON w.activity_id = a.id "
        "WHERE w.activity_id IS NULL "
        "ORDER BY a.start_time DESC LIMIT ?",
        (limit,),
    ).fetchall()
    for row in rows:
        start = _parse_start(row)
        if start is None:
            stats.skipped += 1
            continue
        day = start.date().isoformat()
        payload = _get(_BASE, {
            "latitude": settings.home_latitude,
            "longitude": settings.home_longitude,
            "start_date": day,
            "end_date": day,
            "hourly": _HOURLY,
            "timezone": "UTC",
        }, client=client)
        if payload is None:
            stats.skipped += 1
            continue
        hourly = payload.get("hourly") or {}
        times = hourly.get("time") or []
        idx = _nearest_hour_index(times, start)
        if idx is None:
            stats.skipped += 1
            continue

        def _pick(key: str) -> float | None:
            values = hourly.get(key)
            if not isinstance(values, list) or idx >= len(values):
                return None
            value = values[idx]
            return float(value) if value is not None else None

        conn.execute(
            "INSERT OR REPLACE INTO activity_weather (activity_id, temp_c, feels_like_c, "
            "dew_point_c, humidity_pct, wind_m_s, precip_mm, source, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'open-meteo-archive', ?)",
            (
                row["id"],
                _pick("temperature_2m"),
                _pick("apparent_temperature"),
                _pick("dew_point_2m"),
                _pick("relative_humidity_2m"),
                _pick("wind_speed_10m"),
                _pick("precipitation"),
                _now_iso(),
            ),
        )
        stats.activity_rows += 1
    conn.commit()
    return stats


def refresh_day(
    conn: sqlite3.Connection,
    settings: Settings,
    day: date,
    *,
    client: httpx.Client | None = None,
) -> bool:
    """Upsert one row in `weather_day` for the given date. Returns True on
    success."""
    if settings.home_latitude is None or settings.home_longitude is None:
        return False
    payload = _get(_BASE, {
        "latitude": settings.home_latitude,
        "longitude": settings.home_longitude,
        "start_date": day.isoformat(),
        "end_date": day.isoformat(),
        "daily": _DAILY,
        "timezone": "UTC",
    }, client=client)
    if payload is None:
        return False
    d = payload.get("daily") or {}

    def _first(key: str) -> float | None:
        values = d.get(key)
        if not isinstance(values, list) or not values:
            return None
        value = values[0]
        return float(value) if value is not None else None

    conn.execute(
        "INSERT OR REPLACE INTO weather_day (day, temp_min_c, temp_max_c, "
        "apparent_mean_c, dew_point_mean_c, humidity_mean_pct, precip_mm, fetched_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            day.isoformat(),
            _first("temperature_2m_min"),
            _first("temperature_2m_max"),
            _first("apparent_temperature_mean"),
            _first("dew_point_2m_mean"),
            _first("relative_humidity_2m_mean"),
            _first("precipitation_sum"),
            _now_iso(),
        ),
    )
    conn.commit()
    return True
