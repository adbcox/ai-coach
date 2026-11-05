"""Thin wrapper around LiteLLM (OpenAI-compatible) at :4000.

The Studio hosts the model; the Mini only calls it. One call-site, one
model, one tool-calling loop. Everything numeric comes from tools; the
LLM only paraphrases the JSON it was handed.

The tool loop keeps `numbers` -- a de-duplicated list of every tool
result the model saw -- so downstream auditing can confirm the reply
only references tool-provided values (coach_messages.numbers_json).
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from . import tools as _tools
from .prompts import load_system_prompt


@dataclass
class CoachResult:
    reply: str
    tools_used: list[dict[str, Any]] = field(default_factory=list)
    numbers: list[dict[str, Any]] = field(default_factory=list)
    model: str = ""
    duration_ms: int = 0
    rounds: int = 0
    finish_reason: str | None = None


def _read_api_key(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def check_model_available(base_url: str, model: str,
                          api_key: str | None = None,
                          timeout_s: float = 5.0) -> tuple[bool, str]:
    """Call `/v1/models` once at startup. Non-crashing: returns (ok, note)."""
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    url = base_url.rstrip("/") + "/v1/models"
    try:
        r = httpx.get(url, headers=headers, timeout=timeout_s)
        r.raise_for_status()
        ids = {m.get("id") for m in (r.json().get("data") or [])}
        if model in ids:
            return True, f"model '{model}' available"
        return False, f"model '{model}' not in /v1/models; have={sorted(ids)}"
    except Exception as e:  # don't crash boot
        return False, f"litellm /v1/models unreachable: {e.__class__.__name__}: {e}"


def _build_messages(system_prompt: str, user_question: str,
                    context: str | None) -> list[dict[str, Any]]:
    msgs: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    if context:
        msgs.append({"role": "system", "content": f"Context:\n{context}"})
    msgs.append({"role": "user", "content": user_question})
    return msgs


def _dedup_append(acc: list[dict[str, Any]], entry: dict[str, Any]) -> None:
    key = (entry.get("tool"), json.dumps(entry.get("arguments") or {}, sort_keys=True))
    for existing in acc:
        if (existing.get("tool"), json.dumps(existing.get("arguments") or {}, sort_keys=True)) == key:
            return
    acc.append(entry)


def run_tool_loop(conn: sqlite3.Connection, *, question: str,
                   context: str | None,
                   base_url: str, model: str,
                   api_key: str | None,
                   system_prompt: str,
                   max_rounds: int,
                   call_timeout_s: float,
                   endpoint_timeout_s: float,
                   force_tool: str | None = None) -> CoachResult:
    """Drive the tool-calling loop. Caller owns the DB connection + persistence."""
    url = base_url.rstrip("/") + "/v1/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    messages = _build_messages(system_prompt, question, context)
    tools_used: list[dict[str, Any]] = []
    numbers: list[dict[str, Any]] = []
    started = time.monotonic()
    rounds = 0
    finish_reason: str | None = None

    tool_choice: Any = "auto"
    if force_tool is not None:
        tool_choice = {"type": "function", "function": {"name": force_tool}}

    with httpx.Client(timeout=call_timeout_s) as http:
        for round_idx in range(max_rounds):
            rounds = round_idx + 1
            if time.monotonic() - started > endpoint_timeout_s:
                return CoachResult(
                    reply="(coach timed out before producing a reply)",
                    tools_used=tools_used, numbers=numbers,
                    model=model, duration_ms=int((time.monotonic()-started)*1000),
                    rounds=rounds, finish_reason="timeout",
                )

            payload = {
                "model": model,
                "messages": messages,
                "tools": _tools.TOOL_SPECS,
                "tool_choice": tool_choice if round_idx == 0 else "auto",
                "temperature": 0.2,
            }
            try:
                r = http.post(url, headers=headers, json=payload)
                r.raise_for_status()
            except httpx.HTTPError as e:
                return CoachResult(
                    reply=f"(coach upstream error: {e.__class__.__name__})",
                    tools_used=tools_used, numbers=numbers, model=model,
                    duration_ms=int((time.monotonic()-started)*1000),
                    rounds=rounds, finish_reason="upstream_error",
                )

            data = r.json()
            choice = (data.get("choices") or [{}])[0]
            msg = choice.get("message") or {}
            finish_reason = choice.get("finish_reason")
            tool_calls = msg.get("tool_calls") or []

            messages.append({
                "role": "assistant",
                "content": msg.get("content"),
                "tool_calls": tool_calls or None,
            })

            if not tool_calls:
                return CoachResult(
                    reply=(msg.get("content") or "").strip(),
                    tools_used=tools_used, numbers=numbers, model=model,
                    duration_ms=int((time.monotonic()-started)*1000),
                    rounds=rounds, finish_reason=finish_reason,
                )

            for call in tool_calls:
                fn = (call.get("function") or {})
                name = fn.get("name") or ""
                raw_args = fn.get("arguments")
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except (TypeError, ValueError):
                    args = {}
                result = _tools.call_tool(conn, name, args)
                entry = {"tool": name, "arguments": args, "result": result}
                tools_used.append(entry)
                _dedup_append(numbers, entry)
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id") or "",
                    "name": name,
                    "content": json.dumps(result, default=str),
                })

    return CoachResult(
        reply="(coach exhausted tool rounds without producing a final reply)",
        tools_used=tools_used, numbers=numbers, model=model,
        duration_ms=int((time.monotonic()-started)*1000),
        rounds=rounds, finish_reason=finish_reason or "max_rounds",
    )


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def numeric_tokens(text: str) -> set[str]:
    """Extract bare numeric tokens from a reply (for audit regression tests)."""
    return set(_NUM_RE.findall(text or ""))


def numeric_tokens_in_results(results: list[dict[str, Any]]) -> set[str]:
    """Flatten every scalar number present in the tool results."""
    out: set[str] = set()

    def walk(x: Any) -> None:
        if isinstance(x, (int, float)) and not isinstance(x, bool):
            out.add(_NUM_RE.findall(str(x))[0] if _NUM_RE.findall(str(x)) else str(x))
        elif isinstance(x, str):
            for m in _NUM_RE.findall(x):
                out.add(m)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)

    for entry in results:
        walk(entry.get("result"))
    return out


def load_prompt(settings) -> str:
    return load_system_prompt(getattr(settings, "coach_system_prompt_file", None))


def load_api_key(settings) -> str | None:
    return _read_api_key(getattr(settings, "litellm_api_key_file", None))
