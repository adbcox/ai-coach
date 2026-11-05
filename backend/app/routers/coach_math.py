"""P2 coach-maths API — thin GETs reading pre-computed tables + /api/checkin/today.

All routes require a signed-in user. Nothing here does heavy work — the
post-sync hook computes everything into tables; these routes just read.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field


class Checkin(BaseModel):
    overall: int | None = Field(default=None, ge=1, le=5)
    legs: int | None = Field(default=None, ge=1, le=5)
    sleep_feel: int | None = Field(default=None, ge=1, le=5)
    stress: int | None = Field(default=None, ge=1, le=5)
    alcohol_units: float | None = Field(default=None, ge=0, le=50)
    ill: bool | None = None
    note: str | None = Field(default=None, max_length=2000)


def make_router(get_conn, current_user):
    r = APIRouter(dependencies=[Depends(current_user)])

    # ------------------------------ load / PMC ------------------------------

    @r.get("/api/load")
    def load_today(conn=Depends(get_conn)) -> dict:
        today = date.today().isoformat()
        row = conn.execute(
            "SELECT day, trimp, tss, ctl, atl, tsb, acwr FROM training_load_day "
            "WHERE day = ?", (today,),
        ).fetchone()
        if row is None:
            # fall back to the latest day we have
            row = conn.execute(
                "SELECT day, trimp, tss, ctl, atl, tsb, acwr FROM training_load_day "
                "ORDER BY day DESC LIMIT 1",
            ).fetchone()
        return dict(row) if row else {"day": today, "trimp": 0.0, "tss": 0.0,
                                      "ctl": None, "atl": None, "tsb": None, "acwr": None}

    @r.get("/api/load/history")
    def load_history(days: int = 90, family: str | None = None, conn=Depends(get_conn)) -> dict:
        days = max(1, min(400, days))
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
        return {"days": [dict(x) for x in reversed(rows)], "family": family}

    @r.get("/api/load/day/{day}")
    def load_day(day: str, conn=Depends(get_conn)) -> dict:
        row = conn.execute(
            "SELECT day, trimp, tss, ctl, atl, tsb, acwr FROM training_load_day "
            "WHERE day = ?", (day,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, f"No load row for {day}.")
        fam_rows = conn.execute(
            "SELECT family, trimp, tss, ctl, atl, tsb FROM training_load_day_family "
            "WHERE day = ?", (day,),
        ).fetchall()
        return {**dict(row), "families": [dict(x) for x in fam_rows]}

    # ------------------------------ readiness -------------------------------

    @r.get("/api/readiness/today")
    def readiness_today(conn=Depends(get_conn)) -> dict:
        today = date.today().isoformat()
        row = conn.execute(
            "SELECT day, score, band, hrv_part, sleep_part, rhr_part, load_part, "
            "checkin_part, inputs_json FROM readiness_day WHERE day = ?", (today,),
        ).fetchone()
        if row is None:
            return {"day": today, "score": None, "band": None}
        import json
        out = dict(row)
        try:
            out["inputs"] = json.loads(out.pop("inputs_json") or "{}")
        except (ValueError, TypeError):
            out["inputs"] = {}
        return out

    @r.get("/api/readiness/history")
    def readiness_history(days: int = 30, conn=Depends(get_conn)) -> dict:
        days = max(1, min(400, days))
        rows = conn.execute(
            "SELECT day, score, band FROM readiness_day ORDER BY day DESC LIMIT ?",
            (days,),
        ).fetchall()
        return {"days": [dict(x) for x in reversed(rows)]}

    # ------------------------------ activities ------------------------------

    @r.get("/api/activities/{activity_id}/metrics")
    def activity_metrics(activity_id: int, conn=Depends(get_conn)) -> dict:
        row = conn.execute(
            "SELECT * FROM ride_metrics WHERE activity_id = ?", (activity_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "No metrics for this activity yet.")
        return dict(row)

    @r.get("/api/activities/{activity_id}/intervals")
    def activity_intervals(activity_id: int, conn=Depends(get_conn)) -> dict:
        rows = conn.execute(
            "SELECT idx, start_offset_s, end_offset_s, work_or_rest, avg_hr, avg_power, "
            "avg_pace FROM detected_intervals WHERE activity_id = ? ORDER BY idx",
            (activity_id,),
        ).fetchall()
        return {"activity_id": activity_id, "intervals": [dict(r) for r in rows]}

    @r.get("/api/activities/{activity_id}/climbs")
    def activity_climbs(activity_id: int, conn=Depends(get_conn)) -> dict:
        rows = conn.execute(
            "SELECT idx, start_offset_s, end_offset_s, length_m, avg_gradient, "
            "max_gradient, vam FROM climbs WHERE activity_id = ? ORDER BY idx",
            (activity_id,),
        ).fetchall()
        return {"activity_id": activity_id, "climbs": [dict(r) for r in rows]}

    @r.get("/api/activities/{activity_id}/power_curve")
    def activity_power_curve(activity_id: int, conn=Depends(get_conn)) -> dict:
        power_rows = conn.execute(
            "SELECT window_s, watts FROM mean_max_power WHERE activity_id = ? "
            "ORDER BY window_s", (activity_id,),
        ).fetchall()
        pace_rows = conn.execute(
            "SELECT window_s, metres_per_s FROM mean_max_pace WHERE activity_id = ? "
            "ORDER BY window_s", (activity_id,),
        ).fetchall()
        return {"activity_id": activity_id,
                "power": [dict(r) for r in power_rows],
                "pace": [dict(r) for r in pace_rows]}

    # ------------------------------ VDOT + staleness ------------------------

    @r.get("/api/vdot/state")
    def vdot_state_route(conn=Depends(get_conn)) -> dict:
        from ..coach_maths import vdot_state
        state = vdot_state.current(conn)
        events = conn.execute(
            "SELECT day, delta, reason FROM vdot_events ORDER BY id DESC LIMIT 10",
        ).fetchall()
        return {"state": state, "recent_events": [dict(r) for r in events]}

    @r.get("/api/thresholds/staleness")
    def thresholds_staleness(conn=Depends(get_conn)) -> dict:
        rows = conn.execute(
            "SELECT sport_key, stored, suggested, evidence_json, computed_at "
            "FROM thresholds_staleness ORDER BY sport_key",
        ).fetchall()
        import json
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["evidence"] = json.loads(d.pop("evidence_json") or "{}")
            except (ValueError, TypeError):
                d["evidence"] = {}
            out.append(d)
        return {"stale": out}

    # ------------------------------ check-in --------------------------------

    @r.get("/api/checkin/today")
    def checkin_today(conn=Depends(get_conn)) -> dict:
        today = date.today().isoformat()
        row = conn.execute(
            "SELECT day, overall, legs, sleep_feel, stress, alcohol_units, ill, note "
            "FROM checkins WHERE day = ?", (today,),
        ).fetchone()
        return dict(row) if row else {"day": today}

    @r.post("/api/checkin/today")
    def checkin_post(body: Checkin, conn=Depends(get_conn)) -> dict:
        today = date.today().isoformat()
        conn.execute(
            "INSERT INTO checkins (day, overall, legs, sleep_feel, stress, alcohol_units, "
            "ill, note, created_at) VALUES (?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(day) DO UPDATE SET overall=excluded.overall, legs=excluded.legs, "
            "sleep_feel=excluded.sleep_feel, stress=excluded.stress, "
            "alcohol_units=excluded.alcohol_units, ill=excluded.ill, note=excluded.note",
            (today, body.overall, body.legs, body.sleep_feel, body.stress,
             body.alcohol_units, 1 if body.ill else 0, body.note,
             datetime.now(UTC).isoformat(timespec="seconds")),
        )
        conn.commit()
        try:
            from ..coach_maths import readiness
            readiness.recompute_today(conn)
        except Exception:
            pass
        return {"ok": True, "day": today}

    # ------------------------------ P2b: correlations / disagreement / weather / suggest ---

    @r.get("/api/correlations")
    def correlations(y: str | None = None, min_abs_rho: float = 0.25,
                     limit: int = 20, conn=Depends(get_conn)) -> dict:
        from ..coach_maths import correlate
        rows = correlate.top_for(conn, y=y, min_abs_rho=min_abs_rho, limit=limit)
        return {"rows": rows, "note": "association, not cause"}

    @r.get("/api/activities/{activity_id}/disagreement")
    def ride_disagreement(activity_id: int, conn=Depends(get_conn)) -> dict:
        row = conn.execute(
            "SELECT activity_id, disagreement_score, cause, confidence, "
            "evidence_json, computed_at FROM ride_disagreement "
            "WHERE activity_id = ?", (activity_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "No disagreement row for this activity.")
        import json
        d = dict(row)
        try:
            d["evidence"] = json.loads(d.pop("evidence_json") or "{}")
        except (ValueError, TypeError):
            d["evidence"] = {}
        return d

    @r.get("/api/weather/day/{day}")
    def weather_day_route(day: str, conn=Depends(get_conn)) -> dict:
        row = conn.execute(
            "SELECT day, temp_min_c, temp_max_c, apparent_mean_c, dew_point_mean_c, "
            "humidity_mean_pct, precip_mm, fetched_at FROM weather_day WHERE day = ?",
            (day,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, f"No weather for {day}.")
        return dict(row)

    @r.get("/api/weather/activity/{activity_id}")
    def weather_for_activity(activity_id: int, conn=Depends(get_conn)) -> dict:
        row = conn.execute(
            "SELECT aw.activity_id, a.start_time, aw.feels_like_c, aw.temp_c, "
            "aw.dew_point_c, aw.humidity_pct, aw.wind_m_s, aw.precip_mm, "
            "aw.source, aw.fetched_at "
            "FROM activity_weather aw "
            "LEFT JOIN activities a ON a.id = aw.activity_id "
            "WHERE aw.activity_id = ?",
            (activity_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "No weather for this activity.")
        return dict(row)

    @r.get("/api/suggest/routine")
    def routine_profile_route(conn=Depends(get_conn)) -> dict:
        from ..coach_maths import routine as _routine
        latest = _routine.latest(conn)
        if latest is None:
            raise HTTPException(404, "No routine profile computed yet.")
        return latest

    @r.get("/api/suggest/today")
    def suggest_today_route(conn=Depends(get_conn)) -> dict:
        from ..coach_maths import suggest
        return suggest.suggest_today(conn)

    @r.post("/api/suggest/today")
    def suggest_feedback(
        user_action: str = Body(..., embed=True, pattern="^(did_it|swapped|ignored)$"),
        conn=Depends(get_conn),
    ) -> dict:
        today = date.today().isoformat()
        row = conn.execute(
            "SELECT id FROM suggestion_history WHERE day = ? ORDER BY id DESC LIMIT 1",
            (today,),
        ).fetchone()
        if row is None:
            raise HTTPException(404, "No suggestion recorded for today.")
        from ..coach_maths import suggest
        suggest.record_feedback(conn, int(row["id"]), user_action)
        return {"ok": True, "suggestion_id": int(row["id"])}

    return r
