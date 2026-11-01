"""Body measurements from stored Garmin weight data, plus the profile helpers (age, sex).

Garmin's weight service returns grams. The exact JSON layout is read defensively: the app looks for the
newest entry that carries a weight in any of the places Garmin is known to put it, and says so plainly
when it finds none. A value typed in Settings always wins over Garmin's.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import Any


def _kg(value: Any) -> float | None:
    """Garmin sends grams (e.g. 63502.0); accept kilograms too if the number is small."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    kg = v / 1000.0 if v > 400 else v
    return round(kg, 1) if 25 <= kg <= 300 else None


def _entry_weight(entry: dict[str, Any]) -> float | None:
    latest = entry.get("latestWeight")
    if isinstance(latest, dict):
        kg = _kg(latest.get("weight"))
        if kg:
            return kg
    metrics = entry.get("allWeightMetrics")
    if isinstance(metrics, list):
        for m in reversed(metrics):
            kg = _kg(m.get("weight")) if isinstance(m, dict) else None
            if kg:
                return kg
    for key in ("weight", "maxWeight", "minWeight"):
        kg = _kg(entry.get(key))
        if kg:
            return kg
    return None


def weight_history(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Daily weights (kg), oldest first, one per calendar day."""
    days: dict[str, float] = {}
    rows = conn.execute("SELECT payload FROM wellness_raw WHERE kind='weight' AND is_empty=0").fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except (TypeError, ValueError):
            continue
        for entry in (payload.get("dailyWeightSummaries") or []) if isinstance(payload, dict) else []:
            if not isinstance(entry, dict):
                continue
            day = entry.get("summaryDate") or (entry.get("latestWeight") or {}).get("calendarDate")
            kg = _entry_weight(entry)
            if day and kg:
                days[str(day)[:10]] = kg
    return [{"date": d, "kg": days[d]} for d in sorted(days)]


def latest_garmin_weight(conn: sqlite3.Connection) -> dict[str, Any] | None:
    hist = weight_history(conn)
    return {"kg": hist[-1]["kg"], "date": hist[-1]["date"]} if hist else None


def age_from_birth_year(birth_year: int | None, today: date | None = None) -> int | None:
    """Age in whole years at the end of the birth year's anniversary is unknown, so this is year-based (+/- 1)."""
    if not birth_year:
        return None
    return (today or date.today()).year - birth_year
