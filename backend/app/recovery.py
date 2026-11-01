"""Daily recovery metrics parsed from the stored raw Garmin payloads.

Shapes were taken from a real account (see docs/garmin.md). Everything is read
defensively: a missing or oddly shaped field becomes None, never an error.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from .wellness import SOURCE, _dig


def _hours(seconds: Any) -> float | None:
    return round(seconds / 3600, 2) if isinstance(seconds, (int, float)) else None


def _put(days: dict[str, dict[str, Any]], day: Any, **values: Any) -> None:
    if not isinstance(day, str) or len(day) < 10:
        return
    row = days.setdefault(day[:10], {"date": day[:10]})
    for key, value in values.items():
        if value is not None and row.get(key) is None:  # first source to provide a value wins
            row[key] = value


def build(conn, days: int = 90) -> list[dict[str, Any]]:
    since = (date.today() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        "SELECT kind, start_date, payload FROM wellness_raw WHERE source=? AND is_empty=0 "
        "AND end_date >= ? ORDER BY start_date DESC", (SOURCE, since)).fetchall()
    out: dict[str, dict[str, Any]] = {}

    def load(row) -> Any:
        try:
            return json.loads(row["payload"])
        except ValueError:
            return None

    # Order of preference per field: the detailed per-day payloads first, summaries fill gaps.
    for kind in ("sleep", "hrv", "hrv_summaries", "daily_summaries", "sleep_summaries", "steps"):
        for row in (r for r in rows if r["kind"] == kind):
            p = load(row)
            if kind in ("sleep", "sleep_summaries"):
                items = [p] if kind == "sleep" else (p if isinstance(p, list) else [])
                for s in items:
                    if not isinstance(s, dict) or not s.get("sleepTimeSeconds"):
                        continue
                    _put(out, s.get("calendarDate") or row["start_date"],
                         sleep_score=_dig(s, "sleepScores", "overall", "value"),
                         sleep_h=_hours(s.get("sleepTimeSeconds")),
                         deep_h=_hours(s.get("deepSleepSeconds")),
                         rem_h=_hours(s.get("remSleepSeconds")),
                         light_h=_hours(s.get("lightSleepSeconds")),
                         awake_h=_hours(s.get("awakeSleepSeconds")),
                         sleep_hr=s.get("avgHeartRate"),
                         sleep_stress=s.get("avgSleepStress"),
                         sleep_need_h=(_dig(s, "sleepNeed", "actual") or 0) / 60 or None)
            elif kind == "hrv":
                h = _dig(p, "hrvSummary")
                if isinstance(h, dict):
                    _put(out, h.get("calendarDate"), hrv=h.get("lastNightAvg"),
                         hrv_weekly=h.get("weeklyAvg"), hrv_status=h.get("status"),
                         hrv_low=_dig(h, "baseline", "balancedLow"),
                         hrv_high=_dig(h, "baseline", "balancedUpper"))
            elif kind == "hrv_summaries":
                for h in _dig(p, "hrvSummaries") or []:
                    if isinstance(h, dict):
                        _put(out, h.get("calendarDate"), hrv=h.get("lastNightAvg"),
                             hrv_weekly=h.get("weeklyAvg"), hrv_status=h.get("status"),
                             hrv_low=_dig(h, "baseline", "balancedLow"),
                             hrv_high=_dig(h, "baseline", "balancedUpper"))
            elif kind == "daily_summaries":
                for d in _dig(p, "data") or []:
                    if not isinstance(d, dict):
                        continue
                    _put(out, d.get("calendarDate"),
                         resting_hr=_dig(d, "heartRate", "restingValue"),
                         bb_max=_dig(d, "bodyBattery", "maxValue"),
                         bb_min=_dig(d, "bodyBattery", "minValue"),
                         bb_charged=_dig(d, "bodyBattery", "chargedValue"),
                         bb_drained=_dig(d, "bodyBattery", "drainedValue"),
                         stress_avg=(lambda v: v if isinstance(v, (int, float)) and v >= 0 else None)(
                             _dig(d, "stress", "avgLevel")),
                         steps=_dig(d, "movement", "steps", "value"),
                         intensity_min=(lambda m, v: (m or 0) + 2 * (v or 0) if m is not None
                                        or v is not None else None)(
                             _dig(d, "intensityMinutes", "moderate"),
                             _dig(d, "intensityMinutes", "vigorous")),
                         respiration=_dig(d, "respiration", "avgValue"),
                         spo2=_dig(d, "pulseOx", "avgValue"))
            elif kind == "steps":
                for d in p if isinstance(p, list) else []:
                    if isinstance(d, dict):
                        _put(out, d.get("calendarDate"), steps=d.get("totalSteps"))
    # per-day heart-rate payloads carry a resting HR too (fills any gaps)
    for row in (r for r in rows if r["kind"] == "heart_rate"):
        p = load(row)
        _put(out, _dig(p, "calendarDate") or row["start_date"], resting_hr=_dig(p, "restingHeartRate"))
    return [out[d] for d in sorted(out) if d >= since]
