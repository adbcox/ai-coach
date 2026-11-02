"""Laps (Garmin Connect's "splits") for each activity, read from the FIT file Garmin sent.

New activities get their laps when they are downloaded. Activities stored before laps were kept are filled in by a background
pass over the FIT files already on disk (no new Garmin requests).
"""

from __future__ import annotations

import sqlite3
import statistics
from datetime import UTC, datetime
from typing import Any

from .fit.parser import FitError, Lap, extract_fit, parse_laps

LAP_VERSION = 1


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def save_laps(conn: sqlite3.Connection, activity_id: int, laps: list[Lap]) -> None:
    conn.execute("DELETE FROM laps WHERE activity_id=?", (activity_id,))
    conn.executemany(
        "INSERT OR REPLACE INTO laps (activity_id, idx, start_t, elapsed_s, timer_s, distance_m, avg_speed, max_speed, avg_hr, "
        "max_hr, ascent_m, descent_m, avg_cadence, avg_power, trigger, intensity) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [(activity_id, lap.index, lap.start_t, lap.elapsed_s, lap.timer_s, lap.distance_m, lap.avg_speed, lap.max_speed, lap.avg_hr,
          lap.max_hr, lap.ascent_m, lap.descent_m, lap.avg_cadence, lap.avg_power, lap.trigger, lap.intensity) for lap in laps])
    conn.execute("INSERT OR REPLACE INTO lap_scan (activity_id, scanned_at, version, laps) VALUES (?,?,?,?)",
                 (activity_id, _now(), LAP_VERSION, len(laps)))


def pending(conn: sqlite3.Connection) -> list[int]:
    return [r["id"] for r in conn.execute(
        "SELECT a.id FROM activities a LEFT JOIN lap_scan s ON s.activity_id=a.id "
        "WHERE a.file_path IS NOT NULL AND (s.activity_id IS NULL OR s.version<>?) ORDER BY a.start_time DESC", (LAP_VERSION,))]


def scan_one(conn: sqlite3.Connection, settings: Any, activity_id: int) -> None:
    row = conn.execute("SELECT file_path FROM activities WHERE id=?", (activity_id,)).fetchone()
    laps: list[Lap] = []
    if row and row["file_path"]:
        try:
            laps = parse_laps(extract_fit((settings.data_dir / row["file_path"]).read_bytes()))
        except (FitError, OSError):
            pass  # a missing or unreadable file simply has no laps; it is not retried until the version changes
    save_laps(conn, activity_id, laps)
    conn.commit()


def scan_pending(conn: sqlite3.Connection, settings: Any) -> int:
    ids = pending(conn)
    for aid in ids:
        scan_one(conn, settings, aid)
    return len(ids)


def get_laps(conn: sqlite3.Connection, activity_id: int) -> dict[str, Any]:
    act = conn.execute("SELECT sport, start_time FROM activities WHERE id=?", (activity_id,)).fetchone()
    if act is None:
        raise KeyError(activity_id)
    scanned = conn.execute("SELECT 1 FROM lap_scan WHERE activity_id=?", (activity_id,)).fetchone() is not None
    rows = conn.execute("SELECT * FROM laps WHERE activity_id=? ORDER BY idx", (activity_id,)).fetchall()
    running = "run" in (act["sport"] or "").lower()
    first = rows[0]["start_t"] if rows else None
    out = []
    for r in rows:
        d, t = r["distance_m"], r["timer_s"] or r["elapsed_s"]
        speed = r["avg_speed"] or (d / t if d and t else None)
        out.append({
            "n": r["idx"] + 1, "start_offset_s": (r["start_t"] - first) if r["start_t"] is not None and first is not None else None,
            "distance_m": d, "time_s": t, "elapsed_s": r["elapsed_s"], "avg_speed": speed,
            "pace_s_per_km": (1000.0 / speed) if speed and speed > 0.3 else None,
            "avg_hr": r["avg_hr"], "max_hr": r["max_hr"], "ascent_m": r["ascent_m"], "descent_m": r["descent_m"],
            # FIT stores running cadence as strides per minute (one foot); Garmin Connect shows steps per minute (both feet).
            "cadence_spm": (r["avg_cadence"] * 2 if running else r["avg_cadence"]) if r["avg_cadence"] else None,
            "avg_power": r["avg_power"], "trigger": r["trigger"], "intensity": r["intensity"],
        })
    triggers = [lap["trigger"] for lap in out]
    dist_laps = [lap["distance_m"] for lap in out if lap["trigger"] == "distance" and lap["distance_m"]]
    workout = any(lap["intensity"] not in (None, "active") for lap in out)
    if workout:
        kind = "workout"
    elif triggers and triggers.count("distance") >= max(1, len(triggers) - 1):
        kind = "auto_distance"
    elif out:
        kind = "manual"
    else:
        kind = "none"
    # Only rank full-length automatic splits: a short final remainder or a warm-up is not comparable with a 1 km split.
    full = 0.95 * statistics.median(dist_laps) if dist_laps and kind == "auto_distance" else None
    paces = [(lap["pace_s_per_km"], lap["n"]) for lap in out
             if full and lap["pace_s_per_km"] and (lap["distance_m"] or 0) >= full]
    return {"scanned": scanned, "count": len(out), "kind": kind,
            "auto_distance_m": round(statistics.median(dist_laps)) if dist_laps else None,
            "fastest_lap": min(paces)[1] if paces else None, "slowest_lap": max(paces)[1] if paces else None,
            "running": running, "laps": out}
