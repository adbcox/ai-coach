"""Threshold staleness detector.

D1: manual FTP / LTHR / threshold pace / CSS values are **truth**. This module
flags when recent best efforts suggest the stored value is out of date, writes
a suggestion with evidence, but NEVER overwrites the user's stored value.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from .sport import family_for


# Evidence window: look back this many days for recent bests.
EVIDENCE_WINDOW_DAYS = 60
# Margin to call a stored threshold "clearly stale".
FTP_STALE_RATIO = 1.03         # recent 20-min average > 1.03 × FTP
LTHR_STALE_BPM = 3             # recent HR peak > LTHR + 3 bpm at threshold effort
PACE_STALE_RATIO = 0.98        # recent threshold pace < 0.98 × stored (faster)
CSS_STALE_RATIO = 0.98


def _th(conn, key: str) -> float | None:
    row = conn.execute("SELECT value FROM sync_state WHERE key = ?", (key,)).fetchone()
    if row is None or row[0] in (None, ""):
        return None
    try:
        return float(row[0])
    except ValueError:
        return None


def recompute_all(conn) -> list[dict]:
    """Rebuild thresholds_staleness; return the list of flagged rows (if any)."""
    conn.execute("DELETE FROM thresholds_staleness")
    now_iso = datetime.now(UTC).isoformat(timespec="seconds")
    cutoff = (date.today() - timedelta(days=EVIDENCE_WINDOW_DAYS)).isoformat()
    flags: list[dict] = []
    sports = {r["key"] for r in conn.execute("SELECT key FROM sports").fetchall()}
    for key in sports or {"running", "cycling", "lap_swimming"}:
        fam = family_for(key)
        out = _check(conn, fam, cutoff)
        if out is not None:
            stored, suggested, evidence = out
            conn.execute(
                "INSERT INTO thresholds_staleness (sport_key, stored, suggested, evidence_json, "
                "computed_at) VALUES (?,?,?,?,?)",
                (key, stored, suggested, json.dumps(evidence), now_iso),
            )
            flags.append({"sport_key": key, "stored": stored, "suggested": suggested,
                          "evidence": evidence})
    conn.commit()
    return flags


def _check(conn, family: str, cutoff: str) -> tuple[float, float, dict] | None:
    if family in ("bike_road", "bike_indoor", "bike_trail"):
        stored = _th(conn, f"thresholds.{family}.ftp") or _th(conn, "thresholds.ftp")
        if not stored:
            return None
        row = conn.execute(
            "SELECT MAX(watts) AS w FROM mean_max_power mp JOIN activities a "
            "ON a.id = mp.activity_id WHERE mp.window_s = 1200 AND a.start_time >= ?",
            (cutoff,),
        ).fetchone()
        best_20 = row["w"] if row and row["w"] else None
        if best_20 and best_20 >= stored * FTP_STALE_RATIO:
            suggested = best_20 * 0.95
            return stored, suggested, {"metric": "20min_best_w", "value": best_20,
                                       "window_days": EVIDENCE_WINDOW_DAYS}
        return None
    if family in ("run_road", "run_trail"):
        stored = _th(conn, f"thresholds.{family}.threshold_pace_s_per_m") or \
            _th(conn, "thresholds.threshold_pace_s_per_m")
        if not stored:
            return None
        row = conn.execute(
            "SELECT MIN(1.0 / metres_per_s) AS p FROM mean_max_pace mp "
            "JOIN activities a ON a.id = mp.activity_id "
            "WHERE mp.window_s = 1800 AND a.start_time >= ? AND mp.metres_per_s > 0",
            (cutoff,),
        ).fetchone()
        best_pace = row["p"] if row and row["p"] else None
        if best_pace and best_pace <= stored * PACE_STALE_RATIO:
            suggested = best_pace * 1.02
            return stored, suggested, {"metric": "30min_best_pace_s_m", "value": best_pace,
                                       "window_days": EVIDENCE_WINDOW_DAYS}
        return None
    if family in ("swim_pool", "swim_open"):
        stored = _th(conn, f"thresholds.{family}.css_s_per_m") or _th(conn, "thresholds.css_s_per_m")
        if not stored:
            return None
        row = conn.execute(
            "SELECT MIN(1.0 / metres_per_s) AS p FROM mean_max_pace mp "
            "JOIN activities a ON a.id = mp.activity_id "
            "WHERE mp.window_s = 400 AND a.start_time >= ? AND mp.metres_per_s > 0",
            (cutoff,),
        ).fetchone()
        best = row["p"] if row and row["p"] else None
        if best and best <= stored * CSS_STALE_RATIO:
            return stored, best * 1.02, {"metric": "400s_best_pace_s_m", "value": best,
                                         "window_days": EVIDENCE_WINDOW_DAYS}
        return None
    return None
