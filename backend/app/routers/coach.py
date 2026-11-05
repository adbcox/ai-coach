"""P3 coach endpoints — POST /api/coach/{ask, daily, ride/{id}}.

Every endpoint delegates numeric work to tools (coach_maths output
tables) and only uses the LLM to paraphrase. All turns are persisted to
`coach_messages` so audits can confirm the reply only names tool-sourced
numbers.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

from fastapi import APIRouter, Body, Depends, HTTPException

from ..coach import client as _client


def _persist_messages(conn, model: str, result, user_id: int | None,
                       user_text: str) -> None:
    now = datetime.now(UTC).isoformat()
    conn.execute(
        "INSERT INTO coach_messages (user_id, created_at, model, role, text, "
        "tool_calls_json, numbers_json, duration_ms) VALUES (?,?,?,?,?,?,?,?)",
        (user_id, now, model, "user", user_text, None, None, None),
    )
    for entry in result.tools_used:
        conn.execute(
            "INSERT INTO coach_messages (user_id, created_at, model, role, text, "
            "tool_calls_json, numbers_json, duration_ms) VALUES (?,?,?,?,?,?,?,?)",
            (user_id, now, model, "tool", None,
             json.dumps({"tool": entry["tool"], "arguments": entry.get("arguments") or {}}),
             json.dumps(entry.get("result"), default=str), None),
        )
    conn.execute(
        "INSERT INTO coach_messages (user_id, created_at, model, role, text, "
        "tool_calls_json, numbers_json, duration_ms) VALUES (?,?,?,?,?,?,?,?)",
        (user_id, now, model, "assistant", result.reply, None,
         json.dumps([{"tool": e["tool"], "result": e.get("result")}
                      for e in result.numbers], default=str),
         result.duration_ms),
    )
    conn.commit()


def _user_id(user: object | None) -> int | None:
    if user is None:
        return None
    if isinstance(user, dict):
        return user.get("id") or user.get("user_id")
    return getattr(user, "id", None)


def make_router(get_conn, current_user, settings):
    r = APIRouter(dependencies=[Depends(current_user)])

    def _run(conn, question: str, context: str | None,
              force_tool: str | None, user) -> dict:
        model = settings.coach_model
        prompt = _client.load_prompt(settings)
        api_key = _client.load_api_key(settings)
        t0 = time.monotonic()
        result = _client.run_tool_loop(
            conn,
            question=question,
            context=context,
            base_url=settings.litellm_base_url,
            model=model,
            api_key=api_key,
            system_prompt=prompt,
            max_rounds=settings.coach_max_tool_rounds,
            call_timeout_s=settings.coach_call_timeout_s,
            endpoint_timeout_s=settings.coach_endpoint_timeout_s,
            force_tool=force_tool,
        )
        _persist_messages(conn, model, result, _user_id(user), question)
        return {
            "reply": result.reply,
            "tools_used": [{"tool": e["tool"], "arguments": e.get("arguments") or {}}
                           for e in result.tools_used],
            "model": result.model,
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "rounds": result.rounds,
            "finish_reason": result.finish_reason,
        }

    @r.post("/api/coach/ask")
    def ask(
        question: str = Body(..., embed=True, min_length=1, max_length=4000),
        context: str | None = Body(default=None, embed=True, max_length=8000),
        user=Depends(current_user),
        conn=Depends(get_conn),
    ) -> dict:
        return _run(conn, question, context, force_tool=None, user=user)

    @r.post("/api/coach/daily")
    def daily(user=Depends(current_user), conn=Depends(get_conn)) -> dict:
        question = (
            "Give me today's briefing in 3-5 sentences. Call "
            "get_suggested_workout first, then get_readiness and "
            "get_training_load. Quote the top reason and its sample size "
            "verbatim, and mention the alternative if the tool returned one."
        )
        return _run(conn, question, context=None,
                    force_tool="get_suggested_workout", user=user)

    @r.post("/api/coach/ride/{activity_id}")
    def ride(activity_id: int, user=Depends(current_user),
             conn=Depends(get_conn)) -> dict:
        exists = conn.execute(
            "SELECT 1 FROM activities WHERE id = ?", (activity_id,)
        ).fetchone()
        if exists is None:
            raise HTTPException(404, f"activity {activity_id} not found")
        question = (
            f"Short note for activity {activity_id}: what happened and why. "
            f"Call get_activity_metrics, get_disagreement, and "
            f"get_weather_for_activity with activity_id={activity_id}. "
            f"If disagreement is None, say so plainly."
        )
        return _run(conn, question, context=None,
                    force_tool="get_activity_metrics", user=user)

    return r
