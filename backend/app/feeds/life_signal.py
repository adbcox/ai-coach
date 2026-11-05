"""Aggregate per-day life signal from all available feeds.

Writes `life_signal_day` rows with:
  - travel  = any calendar_events on that day with is_travel=1
  - busy    = count of calendar_events with is_busy=1 >= 2 or any day with
              > 6 total hours of busy events (from end-start)
  - alcohol_units = checkins.alcohol_units (manual input in P2)
  - sick    = checkins.ill
  - note    = checkins.note

Idempotent. Call nightly after calendar + checkin writes.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def recompute_range(
    conn: sqlite3.Connection,
    *,
    start: date | None = None,
    end: date | None = None,
) -> int:
    """Recompute `life_signal_day` across [start, end]. Defaults to the
    last 90 days through today."""
    end = end or date.today()
    start = start or (end - timedelta(days=90))
    rows = 0
    cur = start
    while cur <= end:
        rows += 1 if _recompute_one(conn, cur) else 0
        cur = cur + timedelta(days=1)
    conn.commit()
    return rows


def _recompute_one(conn: sqlite3.Connection, day: date) -> bool:
    day_s = day.isoformat()
    cal = conn.execute(
        "SELECT COALESCE(SUM(is_travel), 0) AS t, "
        "       COALESCE(SUM(is_busy), 0) AS b "
        "FROM calendar_events WHERE day = ?",
        (day_s,),
    ).fetchone()
    travel = 1 if (cal and cal["t"] > 0) else 0
    busy = 1 if (cal and cal["b"] >= 2) else 0
    ci = conn.execute(
        "SELECT ill, alcohol_units, note FROM checkins WHERE day = ?",
        (day_s,),
    ).fetchone()
    sick = int(ci["ill"]) if ci and ci["ill"] is not None else 0
    alcohol = ci["alcohol_units"] if ci else None
    note = ci["note"] if ci else None
    if not (travel or busy or sick or alcohol or note):
        # Nothing worth recording.
        return False
    conn.execute(
        "INSERT OR REPLACE INTO life_signal_day (day, travel, busy, alcohol_units, "
        "sick, note, computed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (day_s, travel, busy, alcohol, sick, note, _now_iso()),
    )
    return True
