"""Read-only mirror of Home Assistant history for a small set of entities.

Fetches `GET /api/history/period/<start>` with a Bearer token loaded from
a runtime secret file. Resamples into `ha_series` (every reported sample)
and aggregates a per-day summary into `ha_daily` (bedroom temp/RH overnight,
bed-in/out/wake times from a presence sensor).

Entity names are configurable constants so the deployment can match
Adrian's specific HA setup; defaults are what Adrian named them on the Mini.
"""

from __future__ import annotations

import logging
import sqlite3
import statistics
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx

from ..config import Settings

_LOG = logging.getLogger("feeds.homeassistant")

# These are configurable via env in future; for now, sensible defaults
# that match the plan's wording ("bedroom temp overnight").
BEDROOM_TEMP_ENTITY = "sensor.bedroom_temperature"
BEDROOM_RH_ENTITY = "sensor.bedroom_humidity"
PRESENCE_IN_BED_ENTITY = "binary_sensor.bedroom_occupancy"


@dataclass
class HAStats:
    series_rows: int = 0
    daily_rows: int = 0


def _read_token(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError as exc:
        _LOG.warning("cannot read HA token file %s: %s", path, exc)
        return None


def _get(url: str, token: str, client: httpx.Client | None = None) -> list | dict | None:
    try:
        r = (client or httpx).get(
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=20,
        )
        if r.status_code != 200:
            _LOG.warning("HA fetch %s: HTTP %s", url, r.status_code)
            return None
        return r.json()
    except httpx.HTTPError as exc:
        _LOG.warning("HA fetch failed: %s", exc)
        return None


def _to_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def sync(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    day: date | None = None,
    client: httpx.Client | None = None,
) -> HAStats:
    """Pull the previous 36 hours of history (spans a full sleep period).
    Idempotent."""
    stats = HAStats()
    if settings.hass_token_file is None:
        _LOG.info("HA disabled: AEC_HASS_TOKEN_FILE unset")
        return stats
    token = _read_token(settings.hass_token_file)
    if not token:
        return stats
    end = datetime.now(UTC) if day is None else datetime.combine(
        day + timedelta(days=1), datetime.min.time(), tzinfo=UTC,
    )
    start = end - timedelta(hours=36)
    url = (f"{settings.hass_base_url}/api/history/period/{start.isoformat()}"
           f"?end_time={end.isoformat()}"
           f"&filter_entity_id="
           f"{BEDROOM_TEMP_ENTITY},{BEDROOM_RH_ENTITY},{PRESENCE_IN_BED_ENTITY}")
    payload = _get(url, token, client=client)
    if not isinstance(payload, list):
        return stats
    temp_samples: list[tuple[datetime, float]] = []
    rh_samples: list[tuple[datetime, float]] = []
    presence_samples: list[tuple[datetime, bool]] = []
    for series in payload:
        if not isinstance(series, list) or not series:
            continue
        entity = series[0].get("entity_id") or ""
        for pt in series:
            ts_raw = pt.get("last_changed") or pt.get("last_updated")
            if not ts_raw:
                continue
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            except ValueError:
                continue
            state = pt.get("state")
            value = _to_float(state)
            if value is not None:
                conn.execute(
                    "INSERT OR REPLACE INTO ha_series (entity_id, ts, value) "
                    "VALUES (?, ?, ?)",
                    (entity, ts.isoformat(), value),
                )
                stats.series_rows += 1
            if entity == BEDROOM_TEMP_ENTITY and value is not None:
                temp_samples.append((ts, value))
            elif entity == BEDROOM_RH_ENTITY and value is not None:
                rh_samples.append((ts, value))
            elif entity == PRESENCE_IN_BED_ENTITY:
                presence_samples.append((ts, state == "on"))
    # Compute overnight aggregates for the night that ENDED in the window.
    # Night = 22:00 → 08:00 local (approx via UTC on the start day end).
    night_day = (end - timedelta(hours=18)).date()
    night_start = datetime.combine(night_day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=22)
    night_end = night_start + timedelta(hours=10)
    temps_in = [v for ts, v in temp_samples if night_start <= ts <= night_end]
    rhs_in = [v for ts, v in rh_samples if night_start <= ts <= night_end]
    bed_in_time: str | None = None
    bed_out_time: str | None = None
    wake_time: str | None = None
    presence_in = sorted(
        [(ts, flag) for ts, flag in presence_samples if night_start <= ts <= night_end],
        key=lambda x: x[0],
    )
    if presence_in:
        for ts, flag in presence_in:
            if flag and bed_in_time is None:
                bed_in_time = ts.isoformat()
            if not flag and bed_in_time and bed_out_time is None:
                bed_out_time = ts.isoformat()
                wake_time = ts.isoformat()
                break
    if temps_in or rhs_in or bed_in_time:
        conn.execute(
            "INSERT OR REPLACE INTO ha_daily (day, bedroom_temp_c_night, "
            "bedroom_rh_pct_night, bed_in_time, bed_out_time, wake_time, "
            "computed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                night_day.isoformat(),
                statistics.mean(temps_in) if temps_in else None,
                statistics.mean(rhs_in) if rhs_in else None,
                bed_in_time, bed_out_time, wake_time,
                datetime.now(UTC).isoformat(timespec="seconds"),
            ),
        )
        stats.daily_rows += 1
    conn.commit()
    return stats
