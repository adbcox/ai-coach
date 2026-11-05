"""Tool definitions for the LLM coach.

Every tool is a pure Python function that reads from the SQLite DB (or the
P2b in-memory helpers). The LLM never gets a raw SQL cursor; it only sees
the JSON dicts returned here. Tool schemas (`TOOL_SPECS`) follow the
OpenAI/LiteLLM function-call shape.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, UTC
from typing import Any, Callable


# ---- individual tool implementations --------------------------------------

def get_readiness(conn: sqlite3.Connection, *, day: str | None = None) -> dict:
    d = day or date.today().isoformat()
    row = conn.execute(
        "SELECT day, score, band, hrv_part, sleep_part, rhr_part, load_part, "
        "checkin_part, inputs_json FROM readiness_day WHERE day = ?", (d,),
    ).fetchone()
    if row is None:
        return {"day": d, "score": None, "band": None}
    out = dict(row)
    try:
        out["inputs"] = json.loads(out.pop("inputs_json") or "{}")
    except (TypeError, ValueError):
        out["inputs"] = {}
    return out


def get_training_load(conn: sqlite3.Connection, *, days: int = 28,
                       family: str | None = None) -> dict:
    days = max(1, min(400, int(days)))
    if family:
        rows = conn.execute(
            "SELECT day, trimp, tss, ctl, atl, tsb FROM training_load_day_family "
            "WHERE family = ? ORDER BY day DESC LIMIT ?", (family, days),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT day, trimp, tss, ctl, atl, tsb, acwr FROM training_load_day "
            "ORDER BY day DESC LIMIT ?", (days,),
        ).fetchall()
    return {"family": family, "days": [dict(r) for r in reversed(rows)]}


def get_predictions(conn: sqlite3.Connection) -> dict:
    row = conn.execute(
        "SELECT day, vdot, source, confidence FROM vdot_state "
        "ORDER BY day DESC LIMIT 1",
    ).fetchone()
    return {"vdot": dict(row) if row else None}


def get_activity_metrics(conn: sqlite3.Connection, *, activity_id: int) -> dict:
    row = conn.execute(
        "SELECT * FROM ride_metrics WHERE activity_id = ?", (activity_id,),
    ).fetchone()
    return dict(row) if row else {"activity_id": activity_id, "metrics": None}


def get_best_efforts(conn: sqlite3.Connection, *, sport: str,
                      window_days: int = 90) -> dict:
    cutoff = (date.today() - timedelta(days=int(window_days))).isoformat()
    rows = conn.execute(
        "SELECT window_s, MAX(watts) AS watts FROM mean_max_power mmp "
        "JOIN activities a ON a.id = mmp.activity_id "
        "WHERE a.sport = ? AND a.start_time >= ? "
        "GROUP BY window_s ORDER BY window_s",
        (sport, cutoff),
    ).fetchall()
    return {"sport": sport, "window_days": window_days,
            "power_bests": [dict(r) for r in rows]}


def get_checkin_prompt(conn: sqlite3.Connection) -> dict:
    today = date.today().isoformat()
    row = conn.execute(
        "SELECT day, overall, legs, sleep_feel, stress, alcohol_units, ill, note "
        "FROM checkins WHERE day = ?", (today,),
    ).fetchone()
    return {"day": today, "checkin": dict(row) if row else None,
            "prompt": "How do you feel today? (overall, legs, sleep, stress, alcohol, ill)"}


def get_correlations(conn: sqlite3.Connection, *, y: str,
                      min_abs_rho: float = 0.25, min_n: int = 30) -> dict:
    from ..coach_maths import correlate
    rows = correlate.top_for(conn, y=y, min_abs_rho=float(min_abs_rho),
                             min_n=int(min_n), limit=20)
    return {"y": y, "rows": rows, "note": "association, not cause"}


def get_weather_for_activity(conn: sqlite3.Connection, *, activity_id: int) -> dict:
    row = conn.execute(
        "SELECT aw.activity_id, a.start_time, aw.feels_like_c, aw.temp_c, "
        "aw.dew_point_c, aw.humidity_pct, aw.wind_m_s, aw.precip_mm, "
        "aw.source, aw.fetched_at "
        "FROM activity_weather aw LEFT JOIN activities a ON a.id = aw.activity_id "
        "WHERE aw.activity_id = ?", (activity_id,),
    ).fetchone()
    return dict(row) if row else {"activity_id": activity_id, "weather": None}


def get_disagreement(conn: sqlite3.Connection, *, activity_id: int) -> dict:
    row = conn.execute(
        "SELECT activity_id, disagreement_score, cause, confidence, evidence_json, "
        "computed_at FROM ride_disagreement WHERE activity_id = ?", (activity_id,),
    ).fetchone()
    if row is None:
        return {"activity_id": activity_id, "disagreement": None}
    out = dict(row)
    try:
        out["evidence"] = json.loads(out.pop("evidence_json") or "{}")
    except (TypeError, ValueError):
        out["evidence"] = {}
    return out


def get_thresholds_staleness(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT sport_key, stored, suggested, evidence_json, computed_at "
        "FROM thresholds_staleness ORDER BY sport_key"
    ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["evidence"] = json.loads(d.pop("evidence_json") or "{}")
        except (TypeError, ValueError):
            d["evidence"] = {}
        out.append(d)
    return {"stale": out}


def get_hass_daily(conn: sqlite3.Connection, *, day: str | None = None) -> dict:
    d = day or date.today().isoformat()
    row = conn.execute("SELECT * FROM ha_daily WHERE day = ?", (d,)).fetchone()
    return {"day": d, "ha_daily": dict(row) if row else None}


def get_suggested_workout(conn: sqlite3.Connection, *, day: str | None = None) -> dict:
    from ..coach_maths import suggest
    target = date.fromisoformat(day) if day else None
    return suggest.suggest_today(conn, today=target)


def get_routine_profile(conn: sqlite3.Connection) -> dict:
    from ..coach_maths import routine as _routine
    latest = _routine.latest(conn)
    return {"routine": latest}


# ---- dispatch table + JSON-schema advertisements -------------------------

TOOLS: dict[str, Callable[..., dict]] = {
    "get_readiness": get_readiness,
    "get_training_load": get_training_load,
    "get_predictions": get_predictions,
    "get_activity_metrics": get_activity_metrics,
    "get_best_efforts": get_best_efforts,
    "get_checkin_prompt": get_checkin_prompt,
    "get_correlations": get_correlations,
    "get_weather_for_activity": get_weather_for_activity,
    "get_disagreement": get_disagreement,
    "get_thresholds_staleness": get_thresholds_staleness,
    "get_hass_daily": get_hass_daily,
    "get_suggested_workout": get_suggested_workout,
    "get_routine_profile": get_routine_profile,
}


TOOL_SPECS: list[dict] = [
    {"type": "function", "function": {"name": "get_readiness",
        "description": "Readiness score + band + sub-parts for a given day (defaults to today).",
        "parameters": {"type": "object", "properties": {
            "day": {"type": "string", "description": "YYYY-MM-DD; omit for today."}}}}},
    {"type": "function", "function": {"name": "get_training_load",
        "description": "CTL / ATL / TSB / ACWR over the last `days` (max 400).",
        "parameters": {"type": "object", "properties": {
            "days": {"type": "integer", "default": 28},
            "family": {"type": "string", "description": "Optional sport family (bike_road, run_road, ...)."}}}}},
    {"type": "function", "function": {"name": "get_predictions",
        "description": "Current VDOT state (for running predictions).",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_activity_metrics",
        "description": "NP / IF / TSS / EF / decoupling for one activity.",
        "parameters": {"type": "object", "required": ["activity_id"], "properties": {
            "activity_id": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "get_best_efforts",
        "description": "Rolling power bests for a sport within a window.",
        "parameters": {"type": "object", "required": ["sport"], "properties": {
            "sport": {"type": "string"},
            "window_days": {"type": "integer", "default": 90}}}}},
    {"type": "function", "function": {"name": "get_checkin_prompt",
        "description": "Today's check-in state + a short prompt for the user.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_correlations",
        "description": "Top associations with a y-variable. Labels as association, not cause.",
        "parameters": {"type": "object", "required": ["y"], "properties": {
            "y": {"type": "string", "description": "e.g. 'readiness.score'"},
            "min_abs_rho": {"type": "number", "default": 0.25},
            "min_n": {"type": "integer", "default": 30}}}}},
    {"type": "function", "function": {"name": "get_weather_for_activity",
        "description": "Activity's weather snapshot (feels_like, humidity, wind, etc).",
        "parameters": {"type": "object", "required": ["activity_id"], "properties": {
            "activity_id": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "get_disagreement",
        "description": "Ride power-vs-HR disagreement score + cause + evidence.",
        "parameters": {"type": "object", "required": ["activity_id"], "properties": {
            "activity_id": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "get_thresholds_staleness",
        "description": "Per-sport stored vs suggested thresholds + the evidence.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "get_hass_daily",
        "description": "Home Assistant daily rollup (overnight bedroom temp/RH, in-bed window).",
        "parameters": {"type": "object", "properties": {
            "day": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "get_suggested_workout",
        "description": "Primary + alternative workout pick with component scores, reasons, and sample sizes.",
        "parameters": {"type": "object", "properties": {
            "day": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "get_routine_profile",
        "description": "Latest nightly routine profile: by-weekday/season, rhythm, recurring clusters.",
        "parameters": {"type": "object", "properties": {}}}},
]


def call_tool(conn: sqlite3.Connection, name: str, arguments: dict | None) -> dict:
    """Dispatch a function-call tool invocation. Unknown name → explicit error."""
    fn = TOOLS.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    args = arguments or {}
    try:
        return fn(conn, **args)
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}
    except Exception as e:  # keep the LLM loop alive — report via tool payload
        return {"error": f"{name} failed: {e.__class__.__name__}: {e}"}
