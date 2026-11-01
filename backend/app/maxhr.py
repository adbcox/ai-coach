"""Max heart rate estimated from the athlete's own recorded heart rates, with the working shown."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any

from . import references

WINDOW_DAYS = 730


def get_pref(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM sync_state WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def estimate(conn: sqlite3.Connection, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    since = (now - timedelta(days=WINDOW_DAYS)).isoformat()
    rows = conn.execute(
        "SELECT hp.activity_id, hp.peak_hr, a.start_time, a.sport, a.name FROM hr_peaks hp "
        "JOIN activities a ON a.id=hp.activity_id WHERE a.start_time >= ? AND hp.peak_hr BETWEEN 100 AND 230 "
        "ORDER BY hp.peak_hr DESC LIMIT 8", (since,)).fetchall()
    top = [{"activity_id": r["activity_id"], "date": r["start_time"], "sport": r["sport"], "name": r["name"],
            "peak_hr": round(r["peak_hr"], 1)} for r in rows]
    summary_max = conn.execute("SELECT MAX(max_hr) AS m FROM activities WHERE max_hr BETWEEN 100 AND 230 "
                               "AND start_time >= ?", (since,)).fetchone()["m"]
    by = get_pref(conn, "pref_birth_year")
    age = (now.year - int(by)) if by else None
    tanaka = round(208 - 0.7 * age) if age else None
    out: dict[str, Any] = {"window_days": WINDOW_DAYS, "top_peaks": top, "garmin_summary_max": summary_max,
                           "birth_year": int(by) if by else None, "age": age, "age_formula_tanaka": tanaka,
                           "estimate": None, "confidence": None, "steps": [],
                           "citations": references.get(["tanaka2001", "kasiak2023"])}
    steps = ["For every activity with heart-rate data in the last 2 years the app finds its highest "
             "sustained heart rate: samples outside 40 to 230 bpm are dropped, one-sample spikes (a value more "
             "than 20 bpm from both neighbours while the neighbours agree) are dropped, and the highest "
             "15-second rolling average is kept. This avoids counting wrist-sensor glitches as your maximum."]
    if not top:
        out["steps"] = steps + ["No heart-rate data has been analysed yet."]
        return out
    if len(top) >= 3:
        est = median(p["peak_hr"] for p in top[:3])
        steps += ["Your three highest activity peaks: " + ", ".join(f"{p['peak_hr']:.0f} ({p['date'][:10]})" for p in top[:3]) + ".",
                  f"Estimate = the median of those three = {est:.0f} bpm. Using the median rather than the single "
                  "highest means one stray spike cannot set your maximum."]
        out["confidence"] = "ok"
    else:
        est = top[0]["peak_hr"]
        steps += [f"Only {len(top)} activit{'y' if len(top) == 1 else 'ies'} with usable peaks, so the estimate is the highest "
                  f"({est:.0f} bpm). Low confidence until there are at least 3 hard efforts."]
        out["confidence"] = "low"
    steps.append("This is the highest heart rate you have actually reached, which is only your true maximum if you "
                 "have recently run hard enough to reach it. If your hardest efforts have been moderate it will "
                 "read low.")
    if tanaka:
        steps.append(f"For comparison, the age formula of Tanaka, Monahan & Seals (2001), 208 - 0.7 x age, gives {tanaka} bpm "
                     f"for age {age}. Age formulas carry individual errors of roughly 9 to 10 bpm in endurance athletes "
                     "(Kasiak et al. 2023, 5,069 athletes tested against maximal exercise tests), which is why your own "
                     "recorded peaks are used instead and the formula is only a sanity check.")
    out["estimate"] = round(est)
    out["steps"] = steps
    return out
