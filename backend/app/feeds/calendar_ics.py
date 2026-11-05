"""Read-only mirror of an iCloud shared ICS calendar.

Fetches the URL once, parses with stdlib (no icalendar dep), and writes
each VEVENT into `calendar_events`. Idempotent — the ICS UID becomes the
primary key. Heuristic classification:
  - `is_travel`: summary mentions flight/train/hotel/airport.
  - `is_busy`: event is >= 2 hours long OR summary contains one of a short
    denylist ("meeting", "call", "interview", "appointment").
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from ..config import Settings

_LOG = logging.getLogger("feeds.calendar_ics")

_TRAVEL_RX = re.compile(
    r"\b(flight|flt|airport|train|rail|hotel|airbnb|travel|boarding|gate)\b",
    re.I,
)
_BUSY_RX = re.compile(r"\b(meeting|call|interview|appointment|1:1|standup)\b", re.I)


@dataclass
class CalendarStats:
    inserted: int = 0
    updated: int = 0
    skipped: int = 0


def _read_url_from_file(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        _LOG.warning("cannot read calendar ICS URL file %s: %s", path, exc)
        return None
    if not text.lower().startswith(("http://", "https://", "webcal://")):
        _LOG.warning("calendar ICS URL file %s does not contain a URL", path)
        return None
    return text.replace("webcal://", "https://", 1)


def _fetch(url: str, client: httpx.Client | None = None) -> str | None:
    try:
        r = (client or httpx).get(url, timeout=15,
                                  headers={"User-Agent": "ai-coach/0.6"})
        if r.status_code != 200:
            _LOG.warning("ICS fetch %s: HTTP %s", url, r.status_code)
            return None
        return r.text
    except httpx.HTTPError as exc:
        _LOG.warning("ICS fetch failed: %s", exc)
        return None


def _unfold(raw: str) -> list[str]:
    """ICS line-folding: a leading space/tab continues the previous line."""
    out: list[str] = []
    for line in raw.splitlines():
        if line.startswith((" ", "\t")) and out:
            out[-1] += line[1:]
        else:
            out.append(line)
    return out


def _parse_dt(value: str) -> tuple[datetime | None, str | None]:
    """Return (datetime, day). Handles YYYYMMDD and YYYYMMDDTHHMMSSZ/plain."""
    v = value.strip()
    if not v:
        return None, None
    if len(v) == 8 and v.isdigit():
        y, m, d = int(v[0:4]), int(v[4:6]), int(v[6:8])
        try:
            return datetime(y, m, d, tzinfo=UTC), f"{y:04d}-{m:02d}-{d:02d}"
        except ValueError:
            return None, None
    if "T" in v:
        try:
            if v.endswith("Z"):
                dt = datetime.strptime(v, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            else:
                dt = datetime.strptime(v, "%Y%m%dT%H%M%S")
            return dt, dt.date().isoformat()
        except ValueError:
            return None, None
    return None, None


def _parse_vevents(ics_text: str) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    cur: dict[str, str] | None = None
    for line in _unfold(ics_text):
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT":
            if cur is not None:
                events.append(cur)
            cur = None
        elif cur is not None and ":" in line:
            key, value = line.split(":", 1)
            # Drop parameters after `;` so DTSTART;TZID=... → DTSTART
            key = key.split(";", 1)[0].upper()
            cur[key] = value
    return events


def sync(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    client: httpx.Client | None = None,
) -> CalendarStats:
    stats = CalendarStats()
    if settings.calendar_ics_url_file is None:
        _LOG.info("calendar disabled: AEC_CALENDAR_ICS_URL_FILE unset")
        return stats
    url = _read_url_from_file(settings.calendar_ics_url_file)
    if not url:
        return stats
    ics = _fetch(url, client=client)
    if not ics:
        return stats
    for ev in _parse_vevents(ics):
        uid = ev.get("UID") or ""
        if not uid:
            stats.skipped += 1
            continue
        dtstart, day_s = _parse_dt(ev.get("DTSTART", ""))
        if dtstart is None or day_s is None:
            stats.skipped += 1
            continue
        dtend, _ = _parse_dt(ev.get("DTEND", ""))
        summary = (ev.get("SUMMARY") or "").strip()
        is_travel = 1 if _TRAVEL_RX.search(summary) else 0
        duration_h = ((dtend or dtstart) - dtstart).total_seconds() / 3600.0
        is_busy = 1 if (duration_h >= 2.0 or _BUSY_RX.search(summary)) else 0
        existed = conn.execute(
            "SELECT 1 FROM calendar_events WHERE id = ?", (uid,),
        ).fetchone()
        conn.execute(
            "INSERT OR REPLACE INTO calendar_events (id, day, start_time, end_time, "
            "summary, is_travel, is_busy, source, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'ics', ?)",
            (uid, day_s, dtstart.isoformat(),
             dtend.isoformat() if dtend else None,
             summary, is_travel, is_busy,
             datetime.now(UTC).isoformat(timespec="seconds")),
        )
        if existed:
            stats.updated += 1
        else:
            stats.inserted += 1
    conn.commit()
    return stats
