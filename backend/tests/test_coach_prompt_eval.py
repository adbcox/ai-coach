"""P3 — golden tool-call lists + numeric-audit check.

Uses httpx MockTransport on the LiteLLM endpoint. The mock scripts a small
canonical conversation per question: the first assistant turn calls the
expected tool(s); the second returns prose that only mentions numbers the
tools returned.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.coach import client as coach_client


def _seed(conn):
    conn.execute(
        "INSERT INTO readiness_day (day, score, band, hrv_part, sleep_part, "
        "rhr_part, load_part, checkin_part, inputs_json, computed_at) VALUES "
        "('2026-11-05', 72, 'yellow', 10, 20, 15, 18, 9, '{}', "
        "'2026-11-05T06:00:00+00:00')"
    )
    for d, tss in (("2026-11-03", 50), ("2026-11-04", 80), ("2026-11-05", 20)):
        conn.execute(
            "INSERT INTO training_load_day (day, trimp, tss, ctl, atl, tsb, acwr, computed_at) "
            "VALUES (?, ?, ?, 45, 60, -15, 1.1, '2026-11-05T06:00:00+00:00')",
            (d, tss, tss),
        )
    conn.commit()


def _scripted_transport(script):
    """`script` is a list of dicts: {'tool_calls': [...], 'content': None}
    and finally {'content': 'final text'}. One entry per /chat/completions POST."""
    turns = iter(script)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            try:
                step = next(turns)
            except StopIteration:
                return httpx.Response(500, json={"error": "no more turns"})
            msg = {"role": "assistant",
                   "content": step.get("content"),
                   "tool_calls": step.get("tool_calls")}
            return httpx.Response(200, json={
                "choices": [{"message": msg,
                             "finish_reason": "stop" if step.get("content") else "tool_calls"}],
            })
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def _patch_client(monkeypatch, script):
    transport = _scripted_transport(script)
    original_client = httpx.Client

    def fake_client(*args, **kwargs):
        kwargs["transport"] = transport
        return original_client(*args, **kwargs)

    monkeypatch.setattr(coach_client.httpx, "Client", fake_client)


@pytest.fixture
def seeded_db(authed, settings):
    from app import db
    conn = db.connect(settings.db_path)
    _seed(conn)
    conn.close()
    return settings.db_path


def test_readiness_question_calls_tool_and_numbers_audit(monkeypatch, seeded_db, authed):
    script = [
        {"tool_calls": [{
            "id": "c1",
            "type": "function",
            "function": {"name": "get_readiness",
                         "arguments": json.dumps({"day": "2026-11-05"})},
        }]},
        {"content": "Readiness is 72 (yellow)."},
    ]
    _patch_client(monkeypatch, script)
    r = authed.post("/api/coach/ask", json={"question": "How ready am I?"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tools_used"][0]["tool"] == "get_readiness"
    # every numeric token in the reply appears in the tool results
    reply_nums = coach_client.numeric_tokens(body["reply"])
    assert "72" in reply_nums


def test_training_load_question(monkeypatch, seeded_db, authed):
    script = [
        {"tool_calls": [{
            "id": "c2",
            "type": "function",
            "function": {"name": "get_training_load",
                         "arguments": json.dumps({"days": 3})},
        }]},
        {"content": "CTL is 45, ATL 60, TSB -15."},
    ]
    _patch_client(monkeypatch, script)
    r = authed.post("/api/coach/ask", json={"question": "What's my form?"})
    assert r.status_code == 200
    body = r.json()
    assert body["tools_used"][0]["tool"] == "get_training_load"
    for n in ("45", "60"):
        assert n in body["reply"]


def test_two_round_tool_loop(monkeypatch, seeded_db, authed):
    script = [
        {"tool_calls": [{
            "id": "c1", "type": "function",
            "function": {"name": "get_readiness", "arguments": "{}"},
        }]},
        {"tool_calls": [{
            "id": "c2", "type": "function",
            "function": {"name": "get_training_load",
                         "arguments": json.dumps({"days": 3})},
        }]},
        {"content": "72 yellow, CTL 45."},
    ]
    _patch_client(monkeypatch, script)
    r = authed.post("/api/coach/ask", json={"question": "quick status"})
    assert r.status_code == 200
    body = r.json()
    tools = [t["tool"] for t in body["tools_used"]]
    assert tools == ["get_readiness", "get_training_load"]
    assert body["rounds"] == 3


def test_coach_messages_row_written(monkeypatch, seeded_db, authed, settings):
    script = [
        {"tool_calls": [{
            "id": "c1", "type": "function",
            "function": {"name": "get_readiness", "arguments": "{}"},
        }]},
        {"content": "72 yellow."},
    ]
    _patch_client(monkeypatch, script)
    r = authed.post("/api/coach/ask", json={"question": "status?"})
    assert r.status_code == 200
    from app import db
    conn = db.connect(settings.db_path)
    try:
        rows = conn.execute(
            "SELECT role FROM coach_messages ORDER BY id"
        ).fetchall()
    finally:
        conn.close()
    roles = [r_["role"] for r_ in rows]
    assert "user" in roles and "tool" in roles and "assistant" in roles


def test_upstream_error_returns_safe_reply(monkeypatch, seeded_db, authed):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "upstream down"})

    original_client = httpx.Client

    def fake_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return original_client(*args, **kwargs)

    monkeypatch.setattr(coach_client.httpx, "Client", fake_client)
    r = authed.post("/api/coach/ask", json={"question": "hi"})
    assert r.status_code == 200
    assert "coach upstream error" in r.json()["reply"]
