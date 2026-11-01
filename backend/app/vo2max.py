"""VO2max estimates from the athlete's own data. Several methods side by side, each with its working.

None of these is a measured VO2max (that needs a lab test); they are estimates for tracking trends.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any

from . import maxhr, predict, recovery, references

UTH_FACTOR = 15.3     # Uth et al. 2004: VO2max = 15.3 x HRmax / HRrest (ml/kg/min)
UTH_SEE = 4.7         # reported standard error with age-predicted HRmax (about 7.8%)

CITATION_IDS = ["daniels1979", "uth2004", "molina2022", "firstbeat2017", "frontiers2024_acsm", "elife2023", "tanaka2001", "kasiak2023"]


def build(conn: sqlite3.Connection, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    methods: list[dict[str, Any]] = []

    # 1. VDOT from race performance --------------------------------------------------------------
    efforts = predict.load_efforts(conn, (now - timedelta(days=365)).isoformat(), True, True, True)
    best = predict.best_per_distance([e for e in efforts if predict.RIEGEL_MIN_S <= e["time_s"] <= predict.RIEGEL_MAX_S])
    rows = [(d, e, predict.vdot(d, e["time_s"])) for d, e in sorted(best.items()) if d >= 3000]
    if rows:
        vals = [v for _, _, v in rows]
        mid = median(vals)
        methods.append({
            "id": "vdot", "name": "From race performance (VDOT)", "value": mid, "low": min(vals), "high": max(vals),
            "unit": "VDOT", "status": "ok", "citation": "daniels1979", "source_year": 1979,
            "steps": ["VDOT = oxygen cost of the speed / fraction of VO2max a runner can hold for that duration "
                      "(Daniels & Gilbert equations; see the Predict page for the equations with numbers).",
                      *[f"  {predict.km(d)} in {predict.fmt_time(e['time_s'])} ({e['date'][:10]}) -> VDOT {v:.1f}" for d, e, v in rows],
                      f"Estimate = the median of these ({mid:.1f}); range {min(vals):.1f} to {max(vals):.1f}. "
                      "Shorter efforts often give higher numbers because they are closer to all-out."],
            "warnings": ["VDOT is a performance index that behaves like VO2max in ml/kg/min but is not a measurement of it."]})
    else:
        methods.append({"id": "vdot", "name": "From race performance (VDOT)", "value": None, "status": "not_enough_data",
                        "citation": "daniels1979", "steps": ["Needs at least one 3 km or longer best effort in the last 12 months."],
                        "warnings": []})

    # 2. Heart rate ratio ------------------------------------------------------------------------
    est = maxhr.estimate(conn, now)
    custom = maxhr.get_pref(conn, "pref_max_hr")
    hrmax = int(custom) if custom else est["estimate"]
    rest_days = [d["resting_hr"] for d in recovery.build(conn, 30) if d.get("resting_hr")]
    if hrmax and len(rest_days) >= 7:
        hrrest = median(rest_days)
        v = UTH_FACTOR * hrmax / hrrest
        methods.append({
            "id": "hr_ratio", "name": "Heart rate ratio (resting vs max)", "value": v, "low": v - UTH_SEE, "high": v + UTH_SEE,
            "unit": "ml/kg/min", "status": "ok", "citation": "uth2004", "source_year": 2004,
            "steps": ["Formula: VO2max = 15.3 x HRmax / HRrest.",
                      f"HRmax = {hrmax} bpm ({'your setting' if custom else 'estimated from your own peaks'}).",
                      f"HRrest = {hrrest:.0f} bpm (median of {len(rest_days)} days of resting heart rate in the last 30 days).",
                      f"VO2max = 15.3 x {hrmax} / {hrrest:.0f} = {v:.1f} ml/kg/min",
                      f"Range shown = +/- {UTH_SEE} (the standard error Uth et al. reported when HRmax was age-predicted)."],
            "warnings": ["The 15.3 constant came from 10 well-trained men. Resting-heart-rate based estimates tend to "
                         "read high (INTERLIVE meta-analysis), so treat this as an upper-leaning estimate."]})
    else:
        methods.append({"id": "hr_ratio", "name": "Heart rate ratio (resting vs max)", "value": None, "status": "not_enough_data",
                        "citation": "uth2004", "warnings": [],
                        "steps": ["Needs a max heart rate (from your data or Settings) and at least 7 days of resting heart "
                                  f"rate in the last 30 days; you have HRmax = {hrmax or 'unknown'} and {len(rest_days)} days."]})

    # 3. The watch's own number, entered by the user ---------------------------------------------
    watch = maxhr.get_pref(conn, "pref_watch_vo2max")
    watch_info = None
    if watch:
        w = float(watch)
        watch_info = {"value": w, "entered": maxhr.get_pref(conn, "pref_watch_vo2max_date"),
                      "differences": [{"method": m["name"], "diff": m["value"] - w} for m in methods if m.get("value")]}

    # trend: best VDOT in the 90 days before each of the last 12 month-ends --------------------
    trend = []
    all_efforts = [e for e in predict.load_efforts(conn, (now - timedelta(days=500)).isoformat(), True, True, True)
                   if e["used"] and e["distance_m"] >= 3000 and predict.RIEGEL_MIN_S <= e["time_s"] <= predict.RIEGEL_MAX_S]
    for k in range(11, -1, -1):
        end = now - timedelta(days=30 * k)
        window = [e for e in all_efforts if timedelta(0) <= end - datetime.fromisoformat(e["date"]) <= timedelta(days=90)]
        if window:
            top = max(window, key=lambda e: predict.vdot(e["distance_m"], e["time_s"]))
            trend.append({"date": end.date().isoformat(), "vdot": predict.vdot(top["distance_m"], top["time_s"]),
                          "effort": predict.brief(top)})
    return {"methods": methods, "watch": watch_info, "trend": trend, "citations": references.get(CITATION_IDS),
            "note": "Estimates for tracking trends, not measurements (a lab test is the reference). Both methods here come from older research "
                    "(1979 and 2004). Newer evidence says wearable-style estimates are good for trends but individually uncertain, and that "
                    "the standard running-cost equation behind many submaximal methods is biased in athletes, so the app does not build on it yet.",
            "max_hr": {"value": hrmax, "estimate": est["estimate"]}}
