"""Composite readiness 0-100 (REPORT-02 §3.4).

Weights (re-normalised when inputs missing):
  35% HRV z-score (today vs 60-day baseline; smallest-worthwhile change = 0.5 SD)
  20% last night's sleep score (Garmin value, 0-100)
  15% resting HR vs its 60-day mean (lower = better; negated z-score)
  15% training-load state: TSB + ACWR penalties
  15% subjective check-in (overall + legs; "I'm ill" forces red/0)

Bands: ≥65 green, 45-64 amber, <45 red. Missing parts skip and renormalise.
"""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta


@dataclass
class ReadinessParts:
    hrv: float | None
    sleep: float | None
    rhr: float | None
    load: float | None
    checkin: float | None
    ill: bool = False


def _clip(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _hrv_z_to_part(z: float | None) -> float | None:
    """A +0.5 SD day is "clearly good" → 70; a -0.5 SD day is "clearly off" → 30.
    Unknown → None."""
    if z is None or math.isnan(z) or math.isinf(z):
        return None
    return _clip(50.0 + 40.0 * z, 0.0, 100.0)


def _rhr_z_to_part(z: float | None) -> float | None:
    """Low RHR is good: invert z (negative z → high score)."""
    if z is None or math.isnan(z) or math.isinf(z):
        return None
    return _clip(50.0 - 40.0 * z, 0.0, 100.0)


def _load_part(tsb: float | None, acwr: float | None) -> float | None:
    if tsb is None and acwr is None:
        return None
    base = 60.0
    if tsb is not None:
        # Fresh (>+15) → bonus; buried (<-20) → penalty.
        base += max(-40.0, min(30.0, tsb * 1.2))
    if acwr is not None:
        # Soft ACWR penalty: >1.5 bad, <0.7 detraining but not as bad.
        if acwr > 1.5:
            base -= (acwr - 1.5) * 40.0
        elif acwr < 0.7:
            base -= (0.7 - acwr) * 15.0
    return _clip(base)


def _checkin_part(overall: int | None, legs: int | None, ill: bool) -> float | None:
    if ill:
        return 0.0
    if overall is None and legs is None:
        return None
    vals: list[int] = []
    for v in (overall, legs):
        if v is not None:
            vals.append(max(1, min(5, v)))
    if not vals:
        return None
    mean = sum(vals) / len(vals)
    return _clip((mean - 1.0) * 25.0)   # 1→0, 3→50, 5→100


def compose(parts: ReadinessParts) -> tuple[int, str, dict[str, float | None]]:
    """Return (score 0-100, band, breakdown dict including weights applied)."""
    if parts.ill:
        return 0, "red", {"hrv": parts.hrv, "sleep": parts.sleep, "rhr": parts.rhr,
                          "load": parts.load, "checkin": 0.0, "ill": True}
    weights = {"hrv": 0.35, "sleep": 0.20, "rhr": 0.15, "load": 0.15, "checkin": 0.15}
    values = {
        "hrv": parts.hrv, "sleep": parts.sleep, "rhr": parts.rhr,
        "load": parts.load, "checkin": parts.checkin,
    }
    active = {k: v for k, v in values.items() if v is not None}
    if not active:
        return 50, "amber", values            # nothing to score; neutral
    total_w = sum(weights[k] for k in active)
    score = sum(active[k] * (weights[k] / total_w) for k in active)
    score_i = int(round(_clip(score)))
    band = "green" if score_i >= 65 else ("amber" if score_i >= 45 else "red")
    return score_i, band, values


# ------------------------------- Inputs --------------------------------------


def _row_val(row, col: str):
    """sqlite3.Row supports index access via column name; make it tolerant."""
    try:
        return row[col]
    except (IndexError, KeyError):
        return None


def _rolling_baseline(values: list[float]) -> tuple[float | None, float | None]:
    """Mean + sd of up to the last 60 valid daily values."""
    window = [v for v in values if v is not None][-60:]
    if len(window) < 7:
        return None, None
    try:
        return statistics.mean(window), statistics.pstdev(window)
    except statistics.StatisticsError:
        return None, None


def _hrv_today(conn, today: str) -> tuple[float | None, float | None]:
    """Return (today's HRV, z-score vs 60-day baseline). Reads wellness_raw."""
    rows = conn.execute(
        "SELECT start_date, payload FROM wellness_raw "
        "WHERE kind IN ('hrv', 'hrv_summaries') AND is_empty = 0 "
        "ORDER BY start_date",
    ).fetchall()
    series: list[tuple[str, float]] = []
    for r in rows:
        try:
            p = json.loads(r["payload"])
        except (ValueError, TypeError):
            continue
        val = None
        if isinstance(p, dict):
            if isinstance(p.get("hrvSummary"), dict):
                val = p["hrvSummary"].get("lastNightAvg")
            if val is None and isinstance(p.get("hrvSummaries"), list) and p["hrvSummaries"]:
                val = p["hrvSummaries"][0].get("lastNightAvg")
        if val is None:
            continue
        try:
            series.append((r["start_date"], float(val)))
        except (TypeError, ValueError):
            pass
    today_val = next((v for d, v in series if d == today), None)
    if today_val is None and series:
        today_val = series[-1][1]
    if today_val is None:
        return None, None
    hist = [v for _, v in series]
    mean, sd = _rolling_baseline(hist)
    if mean is None or sd is None or sd <= 0:
        return today_val, None
    import math
    z = (math.log(today_val) - math.log(mean)) / (sd / mean)
    return today_val, z


def _sleep_score_today(conn, today: str) -> float | None:
    row = conn.execute(
        "SELECT payload FROM wellness_raw WHERE kind='sleep' AND is_empty=0 "
        "AND start_date = ? ORDER BY fetched_at DESC LIMIT 1", (today,),
    ).fetchone()
    if row is None:
        return None
    try:
        p = json.loads(row["payload"])
        return float(p["sleepScores"]["overall"]["value"])
    except (ValueError, TypeError, KeyError):
        return None


def _rhr_today(conn, today: str) -> tuple[float | None, float | None]:
    """(today's RHR, z-score vs 60-day baseline from wellness_raw.daily_summaries)."""
    rows = conn.execute(
        "SELECT start_date, payload FROM wellness_raw WHERE kind='daily_summaries' "
        "AND is_empty=0 ORDER BY start_date",
    ).fetchall()
    series: list[tuple[str, float]] = []
    for r in rows:
        try:
            p = json.loads(r["payload"])
        except (ValueError, TypeError):
            continue
        items = p.get("data") if isinstance(p, dict) else None
        if not items:
            continue
        item = items[0]
        rhr = None
        hr = item.get("heartRate") if isinstance(item, dict) else None
        if isinstance(hr, dict):
            rhr = hr.get("restingValue")
        if rhr is None:
            continue
        try:
            series.append((r["start_date"], float(rhr)))
        except (TypeError, ValueError):
            pass
    today_val = next((v for d, v in series if d == today), None)
    if today_val is None and series:
        today_val = series[-1][1]
    if today_val is None:
        return None, None
    hist = [v for _, v in series]
    mean, sd = _rolling_baseline(hist)
    if mean is None or sd is None or sd <= 0:
        return today_val, None
    return today_val, (today_val - mean) / sd


def recompute_today(conn, today: str | None = None) -> dict:
    """Compute readiness for today, persist, and return the row dict."""
    today = today or date.today().isoformat()
    hrv_val, hrv_z = _hrv_today(conn, today)
    sleep_score = _sleep_score_today(conn, today)
    rhr_val, rhr_z = _rhr_today(conn, today)
    row = conn.execute(
        "SELECT tsb, acwr FROM training_load_day WHERE day = ?", (today,),
    ).fetchone()
    tsb = row["tsb"] if row else None
    acwr = row["acwr"] if row else None
    ci = conn.execute(
        "SELECT overall, legs, ill FROM checkins WHERE day = ?", (today,),
    ).fetchone()
    overall = ci["overall"] if ci else None
    legs = ci["legs"] if ci else None
    ill = bool(ci["ill"]) if ci and ci["ill"] is not None else False
    parts = ReadinessParts(
        hrv=_hrv_z_to_part(hrv_z),
        sleep=sleep_score,
        rhr=_rhr_z_to_part(rhr_z),
        load=_load_part(tsb, acwr),
        checkin=_checkin_part(overall, legs, ill),
        ill=ill,
    )
    score, band, _breakdown = compose(parts)
    inputs = {"hrv_val": hrv_val, "hrv_z": hrv_z, "sleep_score": sleep_score,
              "rhr_val": rhr_val, "rhr_z": rhr_z, "tsb": tsb, "acwr": acwr,
              "overall": overall, "legs": legs, "ill": ill}
    conn.execute(
        "INSERT INTO readiness_day (day, score, band, hrv_part, sleep_part, rhr_part, "
        "load_part, checkin_part, inputs_json, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(day) DO UPDATE SET score=excluded.score, band=excluded.band, "
        "hrv_part=excluded.hrv_part, sleep_part=excluded.sleep_part, "
        "rhr_part=excluded.rhr_part, load_part=excluded.load_part, "
        "checkin_part=excluded.checkin_part, inputs_json=excluded.inputs_json, "
        "computed_at=excluded.computed_at",
        (today, score, band, parts.hrv, parts.sleep, parts.rhr, parts.load, parts.checkin,
         json.dumps(inputs), datetime.now(UTC).isoformat(timespec="seconds")),
    )
    conn.commit()
    return {"day": today, "score": score, "band": band, "parts": {
        "hrv": parts.hrv, "sleep": parts.sleep, "rhr": parts.rhr,
        "load": parts.load, "checkin": parts.checkin}, "inputs": inputs}
