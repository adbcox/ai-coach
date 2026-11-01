"""Best efforts: the fastest time the athlete has covered each distance within a run.

Computed from the stored per-second samples with a sliding window over cumulative
distance, so the numbers can be checked by hand: for every start sample, find where
the distance has grown by D, interpolate the exact time, keep the smallest duration.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from typing import Any

from . import db

EFFORT_VERSION = 1  # bump when the algorithm changes; activities are then re-scanned
MARATHON = 42195.0
HALF = 21097.5
DISTANCES = [1000.0, 1609.344, 3000.0, 5000.0, 10000.0, 15000.0, HALF, 30000.0, MARATHON]
MAX_PLAUSIBLE_SPEED = 7.0  # m/s (2:23/km): faster than any 5K world-record pace, so a GPS glitch
GAP_SECONDS = 15           # a pause between samples longer than this counts as a gap


def run_kind(sport: str | None) -> str | None:
    """road / trail / indoor for running activities, None for everything else."""
    s = (sport or "").lower()
    if "run" not in s:
        return None
    if any(k in s for k in ("treadmill", "indoor", "virtual")):
        return "indoor"
    if "trail" in s:
        return "trail"
    return "road"


def best_efforts(t: list[float], d: list[float], hr: list[float | None] | None = None,
                 alt: list[float | None] | None = None) -> list[dict[str, Any]]:
    """Fastest time over each distance in DISTANCES within one activity."""
    n = len(t)
    if n < 2:
        return []
    # cumulative distance must never go backwards (GPS jitter)
    dd = []
    top = d[0]
    for x in d:
        top = max(top, x)
        dd.append(top)
    out: list[dict[str, Any]] = []
    for D in DISTANCES:
        if dd[-1] - dd[0] < D:
            continue
        best: tuple[float, int, int, float] | None = None
        j = 0
        for i in range(n):
            target = dd[i] + D
            j = max(j, i + 1)
            while j < n and dd[j] < target:
                j += 1
            if j >= n:
                break
            d0, d1, t0, t1 = dd[j - 1], dd[j], t[j - 1], t[j]
            tt = t1 if d1 == d0 else t0 + (t1 - t0) * (target - d0) / (d1 - d0)
            dur = tt - t[i]
            if dur > 0 and (best is None or dur < best[0]):
                best = (dur, i, j, tt)
        if best is None:
            continue
        dur, i, j, _ = best
        hrs = [h for h in (hr or [])[i:j + 1] if h]
        gaps = sum(max(0.0, t[k + 1] - t[k] - 1) for k in range(i, j) if t[k + 1] - t[k] > GAP_SECONDS)
        ascent = 0.0
        if alt:
            ref = None
            for a in alt[i:j + 1]:
                if a is None:
                    continue
                if ref is None:
                    ref = a
                elif a - ref >= 2:       # 2 m hysteresis so GPS/baro noise is not counted as climbing
                    ascent += a - ref
                    ref = a
                elif a < ref:
                    ref = a
        out.append({"distance_m": D, "time_s": dur, "start_offset_s": t[i] - t[0],
                    "avg_hr": (sum(hrs) / len(hrs)) if hrs else None, "ascent_m": ascent,
                    "gap_s": gaps, "speed": D / dur})
    return out


def scan_activity(conn: sqlite3.Connection, activity_id: int) -> int:
    rows = conn.execute("SELECT t, dist, hr, alt FROM samples WHERE activity_id=? AND dist IS NOT NULL "
                        "ORDER BY t", (activity_id,)).fetchall()
    conn.execute("DELETE FROM best_efforts WHERE activity_id=?", (activity_id,))
    found = best_efforts([r["t"] for r in rows], [r["dist"] for r in rows],
                         [r["hr"] for r in rows], [r["alt"] for r in rows]) if rows else []
    for e in found:
        conn.execute("INSERT INTO best_efforts (activity_id, distance_m, time_s, start_offset_s, avg_hr, "
                     "ascent_m, gap_s) VALUES (?,?,?,?,?,?,?)",
                     (activity_id, e["distance_m"], e["time_s"], e["start_offset_s"], e["avg_hr"],
                      e["ascent_m"], e["gap_s"]))
    conn.execute("INSERT OR REPLACE INTO effort_scan (activity_id, scanned_at, version) VALUES (?,?,?)",
                 (activity_id, datetime.now(UTC).isoformat(timespec="seconds"), EFFORT_VERSION))
    conn.commit()
    return len(found)


def pending(conn: sqlite3.Connection) -> list[int]:
    ids = []
    for r in conn.execute(
            "SELECT a.id, a.sport FROM activities a LEFT JOIN effort_scan s ON s.activity_id=a.id "
            "WHERE a.has_samples=1 AND (s.activity_id IS NULL OR s.version<>?) ORDER BY a.start_time DESC",
            (EFFORT_VERSION,)):
        if run_kind(r["sport"]):
            ids.append(r["id"])
    return ids


class EffortScanner:
    """Background scan so the first predictions page never blocks on a long computation."""

    def __init__(self, settings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self.total = 0
        self.done = 0

    @property
    def running(self) -> bool:
        return self._lock.locked()

    def start(self) -> bool:
        if not self._lock.acquire(blocking=False):
            return False
        threading.Thread(target=self._run, daemon=True, name="effort-scan").start()
        return True

    def run_blocking(self) -> None:
        if self._lock.acquire(blocking=False):
            self._run()

    def _run(self) -> None:
        try:
            conn = db.connect(self.settings.db_path)
            try:
                ids = pending(conn)
                self.total, self.done = len(ids), 0
                for aid in ids:
                    scan_activity(conn, aid)
                    self.done += 1
            finally:
                conn.close()
        finally:
            self._lock.release()
