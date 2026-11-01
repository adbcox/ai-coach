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

EFFORT_VERSION = 3  # bump when the algorithm changes; activities are then re-scanned
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


# Minetti et al. (2002) J Appl Physiol 93:1039-1046: energy cost of running (J per kg per metre) on a
# slope i (rise/run, e.g. 0.10 = 10%). Fifth-order polynomial as commonly published; valid for -0.45..+0.45.
MINETTI = (155.4, -30.4, -43.3, 46.3, 19.5, 3.6)  # i^5 ... i^0
GRADE_LIMIT = 0.30      # steeper readings are almost always altitude noise, so they are capped here
GRADE_WINDOW_M = 25.0   # grade is measured over +/- 25 m of running to smooth altitude noise


def minetti_cost(i: float) -> float:
    i = max(-0.45, min(0.45, i))
    c = 0.0
    for coef in MINETTI:
        c = c * i + coef
    return c


def cost_ratio(i: float) -> float:
    """How much more (or less) energy a metre costs on grade i than on the flat."""
    return minetti_cost(i) / minetti_cost(0.0)


def grades(d: list[float], alt: list[float | None]) -> list[float]:
    """Grade at each sample from altitude change over +/- GRADE_WINDOW_M of distance (0 if unknown)."""
    n = len(d)
    known = [i for i, a in enumerate(alt) if a is not None]
    if len(known) < 2:
        return [0.0] * n
    a = [None] * n
    last = None
    for i in range(n):                      # forward-fill short altitude gaps
        last = alt[i] if alt[i] is not None else last
        a[i] = last
    first = next(v for v in a if v is not None)
    a = [first if v is None else v for v in a]
    out = [0.0] * n
    lo = hi = 0
    for k in range(n):
        while lo < k and d[lo] < d[k] - GRADE_WINDOW_M:
            lo += 1
        hi = max(hi, k)
        while hi < n - 1 and d[hi] < d[k] + GRADE_WINDOW_M:
            hi += 1
        run = d[hi] - d[lo]
        g = (a[hi] - a[lo]) / run if run >= 10 else 0.0
        out[k] = max(-GRADE_LIMIT, min(GRADE_LIMIT, g))
    return out


def equivalent_distance(d: list[float], alt: list[float | None]) -> list[float]:
    """Cumulative FLAT-EQUIVALENT distance: each step's real distance times Minetti's cost ratio for its grade."""
    g = grades(d, alt)
    eq = [0.0]
    for k in range(1, len(d)):
        step = max(0.0, d[k] - d[k - 1])
        mid = (g[k] + g[k - 1]) / 2
        eq.append(eq[-1] + step * cost_ratio(mid))
    return eq


def best_efforts(t: list[float], d: list[float], hr: list[float | None] | None = None,
                 alt: list[float | None] | None = None, raw_d: list[float] | None = None) -> list[dict[str, Any]]:
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
        covered = (raw_d[j] - raw_d[i]) if raw_d else D
        out.append({"distance_m": D, "time_s": dur, "start_offset_s": t[i] - t[0],
                    "avg_hr": (sum(hrs) / len(hrs)) if hrs else None, "ascent_m": ascent,
                    "gap_s": gaps, "speed": D / dur, "covered_m": covered})
    return out


def hr_peak(t: list[float], hr: list[float | None], window: float = 15.0) -> dict[str, float] | None:
    """Highest sustained heart rate in one activity.

    1. keep samples between 40 and 230 bpm; 2. drop one-sample spikes (a value more than 20 bpm
    away from both neighbours while the neighbours agree within 10 bpm, typical of wrist-sensor
    glitches); 3. average over a rolling 15-second window (needs 5+ samples covering 80% of it);
    4. the activity's peak is the highest of those averages.
    """
    pts = [(ti, h) for ti, h in zip(t, hr, strict=True) if h is not None and 40 <= h <= 230]
    if len(pts) < 5:
        return None
    clean = []
    for k, (ti, h) in enumerate(pts):
        if 0 < k < len(pts) - 1:
            a, b = pts[k - 1][1], pts[k + 1][1]
            if abs(h - a) > 20 and abs(h - b) > 20 and abs(a - b) <= 10:
                continue
        clean.append((ti, h))
    best: tuple[float, float] | None = None
    lo, total = 0, 0.0
    for hi in range(len(clean)):
        total += clean[hi][1]
        while clean[hi][0] - clean[lo][0] > window:
            total -= clean[lo][1]
            lo += 1
        n = hi - lo + 1
        if n >= 5 and clean[hi][0] - clean[lo][0] >= window * 0.8:
            m = total / n
            if best is None or m > best[0]:
                best = (m, clean[hi][0] - clean[0][0])
    return {"peak_hr": best[0], "at_offset_s": best[1], "samples": len(clean)} if best else None


def scan_activity(conn: sqlite3.Connection, activity_id: int) -> int:
    act = conn.execute("SELECT sport FROM activities WHERE id=?", (activity_id,)).fetchone()
    rows = conn.execute("SELECT t, dist, hr, alt FROM samples WHERE activity_id=? ORDER BY t",
                        (activity_id,)).fetchall()
    conn.execute("DELETE FROM best_efforts WHERE activity_id=?", (activity_id,))
    conn.execute("DELETE FROM best_efforts_gap WHERE activity_id=?", (activity_id,))
    conn.execute("DELETE FROM hr_peaks WHERE activity_id=?", (activity_id,))
    found: list[dict[str, Any]] = []
    found_gap: list[dict[str, Any]] = []
    if rows and act and run_kind(act["sport"]):
        with_dist = [r for r in rows if r["dist"] is not None]
        if with_dist:
            tt = [r["t"] for r in with_dist]
            dd = [r["dist"] for r in with_dist]
            hh = [r["hr"] for r in with_dist]
            aa = [r["alt"] for r in with_dist]
            found = best_efforts(tt, dd, hh, aa)
            top = dd[0]
            mono = []
            for x in dd:                    # same monotonic clean-up best_efforts applies internally
                top = max(top, x)
                mono.append(top)
            found_gap = best_efforts(tt, equivalent_distance(mono, aa), hh, aa, raw_d=mono)
    for e in found:
        conn.execute("INSERT INTO best_efforts (activity_id, distance_m, time_s, start_offset_s, avg_hr, "
                     "ascent_m, gap_s) VALUES (?,?,?,?,?,?,?)",
                     (activity_id, e["distance_m"], e["time_s"], e["start_offset_s"], e["avg_hr"],
                      e["ascent_m"], e["gap_s"]))
    for e in found_gap:
        conn.execute("INSERT INTO best_efforts_gap (activity_id, distance_m, time_s, start_offset_s, avg_hr, "
                     "ascent_m, gap_s, covered_m) VALUES (?,?,?,?,?,?,?,?)",
                     (activity_id, e["distance_m"], e["time_s"], e["start_offset_s"], e["avg_hr"],
                      e["ascent_m"], e["gap_s"], e["covered_m"]))
    peak = hr_peak([r["t"] for r in rows], [r["hr"] for r in rows]) if rows else None
    if peak:
        conn.execute("INSERT INTO hr_peaks (activity_id, peak_hr, at_offset_s, samples) VALUES (?,?,?,?)",
                     (activity_id, peak["peak_hr"], peak["at_offset_s"], peak["samples"]))
    conn.execute("INSERT OR REPLACE INTO effort_scan (activity_id, scanned_at, version) VALUES (?,?,?)",
                 (activity_id, datetime.now(UTC).isoformat(timespec="seconds"), EFFORT_VERSION))
    conn.commit()
    return len(found)


def pending(conn: sqlite3.Connection) -> list[int]:
    return [r["id"] for r in conn.execute(
        "SELECT a.id FROM activities a LEFT JOIN effort_scan s ON s.activity_id=a.id "
        "WHERE a.has_samples=1 AND (s.activity_id IS NULL OR s.version<>?) ORDER BY a.start_time DESC",
        (EFFORT_VERSION,))]


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
