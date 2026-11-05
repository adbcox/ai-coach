"""Shared helpers for the bulk importers.

Dedup rule (FORK-PLAN-03 P2b.1): a new row is considered a duplicate of an
existing activity when the two have
  - |start_time delta| <= 60 s, AND
  - |distance delta| <= 50 m or 1.5% (whichever larger), AND
  - |duration delta| <= 30 s or 2% (whichever larger).

When a duplicate is found the new row is skipped and the existing row's
`canonical_id` is set to its own id if not already assigned. This lets
callers link alternate-source copies of the same ride together without
overwriting the first-seen row.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def sha256_of(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@dataclass
class CandidateRow:
    """Minimum metadata needed to run the dedup check."""
    start_time: datetime
    distance_m: float | None
    duration_s: float | None
    sport: str | None = None


def find_duplicate(conn: sqlite3.Connection, cand: CandidateRow) -> int | None:
    """Return the activities.id of a near-match row, or None.

    The query filters on a ±60 s start_time window first (indexed), then
    tightens the match with distance + duration tolerance in Python.
    """
    lo = (cand.start_time.timestamp() - 60.0)
    hi = (cand.start_time.timestamp() + 60.0)
    lo_iso = datetime.fromtimestamp(lo, tz=UTC).isoformat()
    hi_iso = datetime.fromtimestamp(hi, tz=UTC).isoformat()
    rows = conn.execute(
        "SELECT id, start_time, distance_m, duration_s FROM activities "
        "WHERE start_time >= ? AND start_time <= ?",
        (lo_iso, hi_iso),
    ).fetchall()
    for row in rows:
        other_start = _parse_ts(row["start_time"])
        if other_start is None:
            continue
        if abs((other_start - cand.start_time).total_seconds()) > 60.0:
            continue
        if cand.distance_m is not None and row["distance_m"] is not None:
            tol = max(50.0, cand.distance_m * 0.015)
            if abs(row["distance_m"] - cand.distance_m) > tol:
                continue
        if cand.duration_s is not None and row["duration_s"] is not None:
            tol = max(30.0, cand.duration_s * 0.02)
            if abs(row["duration_s"] - cand.duration_s) > tol:
                continue
        return int(row["id"])
    return None


def mark_canonical_link(conn: sqlite3.Connection, keeper_id: int) -> None:
    """Set canonical_id = id on the row we're keeping so follow-up imports
    can find a group leader even without re-running dedup."""
    conn.execute(
        "UPDATE activities SET canonical_id = COALESCE(canonical_id, id) WHERE id = ?",
        (keeper_id,),
    )


def insert_activity(
    conn: sqlite3.Connection,
    *,
    source: str,
    source_id: str,
    start_time: datetime,
    sport: str | None,
    name: str | None,
    distance_m: float | None,
    duration_s: float | None,
    elevation_gain_m: float | None,
    avg_hr: float | None,
    max_hr: float | None,
    file_path: str | None,
    summary: dict[str, Any],
    samples: list[Any] | None,
    laps: list[Any] | None,
) -> int | None:
    """Insert one activity + its samples + laps. Returns the new id or None
    if the (source, source_id) pair is already present."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO activities (source, source_id, start_time, sport, name, "
        "distance_m, duration_s, elevation_gain_m, avg_hr, max_hr, summary_json, file_path, "
        "has_samples, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            source, source_id, start_time.isoformat(), sport, name,
            distance_m, duration_s, elevation_gain_m, avg_hr, max_hr,
            json.dumps(summary), file_path,
            1 if samples else 0, now_iso(),
        ),
    )
    if cur.rowcount == 0:
        return None
    activity_id = int(cur.lastrowid)
    if samples:
        conn.executemany(
            "INSERT OR IGNORE INTO samples (activity_id, t, lat, lon, alt, hr, cadence, "
            "power, speed, dist) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(activity_id, s.t, s.lat, s.lon, s.alt, s.hr, s.cadence, s.power, s.speed, s.dist)
             for s in samples],
        )
    if laps:
        # Lazy import to avoid a circular dep from importers.__init__ at app boot.
        from .. import laps as laps_module
        laps_module.save_laps(conn, activity_id, laps)
    return activity_id


def save_bytes(data: bytes, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_bytes(data)
    return dest
