"""Ride-level power-vs-HR disagreement detector.

Compares the zone distribution of power against HR. When the two medians
disagree by a full zone and the mismatch covers a non-trivial slice of the
ride, we flag a cause and write `ride_disagreement`.

Cause priority (first firing wins):
  stale_threshold  — FTP flagged stale by `thresholds_staleness`
  heat             — activity_weather.feels_like_c >= 24
  fatigue          — training_load_day.tsb < -15 on the ride day
  terrain          — ride is surgy (pacing_cv > 0.35) with a lot of coasting
  unknown          — default
"""

from __future__ import annotations

import json
import math
import sqlite3
import statistics
from datetime import UTC, datetime


THRESHOLD_SCORE_FLAG = 0.6


def _map_zone_6(ord_pct: list[float]) -> int:
    """Given a 7-bucket distribution (0..6), return the median zone 0..6."""
    cumulative = 0.0
    for i, pct in enumerate(ord_pct):
        cumulative += pct
        if cumulative >= 0.5:
            return i
    return len(ord_pct) - 1


def _zone_dist(values: list[float], boundaries: list[float]) -> list[float]:
    """Return 7-bucket distribution. `boundaries` must be length 6, ascending."""
    buckets = [0] * 7
    for v in values:
        if v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        placed = False
        for i, b in enumerate(boundaries):
            if v < b:
                buckets[i] += 1
                placed = True
                break
        if not placed:
            buckets[6] += 1
    total = sum(buckets) or 1
    return [b / total for b in buckets]


def _hr_bounds(lthr: float, max_hr: float | None) -> list[float]:
    # Six boundaries carving the HR axis into 7 buckets. Loosely Friel.
    if max_hr is None or max_hr < lthr * 1.05:
        max_hr = lthr * 1.1
    bounds = [0.70, 0.80, 0.88, 0.95, 1.00, 1.04]
    return [lthr * r for r in bounds]


def _pwr_bounds(ftp: float) -> list[float]:
    # Six boundaries, Coggan 7-zone.
    return [ftp * r for r in (0.55, 0.75, 0.90, 1.05, 1.20, 1.50)]


def _compute_for_activity(conn: sqlite3.Connection, aid: int) -> dict | None:
    row = conn.execute(
        "SELECT a.id, a.sport, a.start_time, "
        "       rm.np, rm.pacing_cv, rm.ef "
        "FROM activities a LEFT JOIN ride_metrics rm ON rm.activity_id = a.id "
        "WHERE a.id = ? ", (aid,),
    ).fetchone()
    if row is None:
        return None
    ftp_row = conn.execute(
        "SELECT value FROM sync_state WHERE key='thresholds.ftp'"
    ).fetchone()
    lthr_row = conn.execute(
        "SELECT value FROM sync_state WHERE key='thresholds.lthr'"
    ).fetchone()
    if ftp_row is None or lthr_row is None:
        return None  # thresholds required; D1 says they're manual
    try:
        ftp = float(ftp_row["value"])
        lthr = float(lthr_row["value"])
    except (TypeError, ValueError):
        return None
    samples = conn.execute(
        "SELECT hr, power FROM samples WHERE activity_id = ? ORDER BY t",
        (aid,),
    ).fetchall()
    hrs = [float(s["hr"]) for s in samples if s["hr"] is not None]
    pwrs = [float(s["power"]) for s in samples if s["power"] is not None]
    if len(hrs) < 60 or len(pwrs) < 60:
        return None
    hr_dist = _zone_dist(hrs, _hr_bounds(lthr, None))
    pwr_dist = _zone_dist(pwrs, _pwr_bounds(ftp))
    hr_med = _map_zone_6(hr_dist)
    pwr_med = _map_zone_6(pwr_dist)
    zone_shift = hr_med - pwr_med
    # Fraction of samples where the two zones disagree outright.
    disagree = sum(1 for h, p in zip(_classify(hrs, _hr_bounds(lthr, None)),
                                     _classify(pwrs, _pwr_bounds(ftp)),
                                     strict=False)
                   if abs(h - p) >= 1)
    frac = disagree / max(min(len(hrs), len(pwrs)), 1)
    score = abs(zone_shift) * frac
    cause = _guess_cause(conn, aid, row, score, ftp)
    evidence = {
        "hr_zone_dist": hr_dist,
        "power_zone_dist": pwr_dist,
        "zone_shift": zone_shift,
        "fraction_disagreeing": round(frac, 3),
    }
    conn.execute(
        "INSERT OR REPLACE INTO ride_disagreement (activity_id, disagreement_score, "
        "cause, confidence, evidence_json, computed_at) VALUES (?, ?, ?, ?, ?, ?)",
        (aid, score, cause, min(1.0, score / 1.0),
         json.dumps(evidence),
         datetime.now(UTC).isoformat(timespec="seconds")),
    )
    return {"activity_id": aid, "score": score, "cause": cause, "evidence": evidence}


def _classify(values: list[float], boundaries: list[float]) -> list[int]:
    out: list[int] = []
    for v in values:
        for i, b in enumerate(boundaries):
            if v < b:
                out.append(i)
                break
        else:
            out.append(6)
    return out


def _guess_cause(conn: sqlite3.Connection, aid: int, row: sqlite3.Row,
                 score: float, ftp: float) -> str | None:
    if score < THRESHOLD_SCORE_FLAG:
        return None
    stale = conn.execute(
        "SELECT suggested FROM thresholds_staleness WHERE sport_key = 'cycling'"
    ).fetchone()
    if stale and stale["suggested"] and stale["suggested"] > ftp * 1.03:
        return "stale_threshold"
    weather = conn.execute(
        "SELECT feels_like_c FROM activity_weather WHERE activity_id = ?",
        (aid,),
    ).fetchone()
    if weather and weather["feels_like_c"] is not None and weather["feels_like_c"] >= 24:
        return "heat"
    tsb_row = conn.execute(
        "SELECT tsb FROM training_load_day WHERE day = date(?)",
        (row["start_time"],),
    ).fetchone()
    if tsb_row and tsb_row["tsb"] is not None and tsb_row["tsb"] < -15:
        return "fatigue"
    pacing_cv = row["pacing_cv"]
    if pacing_cv and pacing_cv > 0.35:
        return "terrain"
    return "unknown"


def recompute_all(conn: sqlite3.Connection) -> int:
    """Scan every ride in `ride_metrics`; writes/updates `ride_disagreement`.
    Returns the number of rows computed."""
    rows = conn.execute(
        "SELECT activity_id FROM ride_metrics WHERE family LIKE 'bike_%' "
        "ORDER BY activity_id DESC",
    ).fetchall()
    n = 0
    for r in rows:
        if _compute_for_activity(conn, r["activity_id"]) is not None:
            n += 1
    conn.commit()
    return n
