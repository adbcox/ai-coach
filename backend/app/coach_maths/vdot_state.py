"""Running VDOT state: current estimate + ±0.5 adjustment events.

Rules (REPORT-02 §3.5):
  * When 2 of the last 3 quality sessions over 21 days consistently come out
    "easier" (≥ 2% faster without HR > LTHR+2%) or "harder" (half the intervals
    ≥ 3% slower or HR > LTHR+5% at prescribed pace), apply ±0.5 VDOT.
  * Max once per week; never within 10 days of goal race.

We don't yet have "quality session" tagging, so this module exposes:
  * `current(conn)` — the latest vdot_state row (dict or None).
  * `record(conn, day, vdot, source, confidence)` — persist a new state.
  * `apply_event(conn, day, delta, reason, sessions)` — record an adjustment
    event and roll forward the state. Respects the weekly rate limit.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta


def current(conn) -> dict | None:
    row = conn.execute(
        "SELECT day, vdot, source, confidence FROM vdot_state ORDER BY day DESC LIMIT 1",
    ).fetchone()
    return dict(row) if row else None


def record(conn, day: str, vdot: float, source: str, confidence: float = 1.0) -> dict:
    conn.execute(
        "INSERT INTO vdot_state (day, vdot, source, confidence) VALUES (?,?,?,?) "
        "ON CONFLICT(day) DO UPDATE SET vdot=excluded.vdot, source=excluded.source, "
        "confidence=excluded.confidence",
        (day, vdot, source, confidence),
    )
    conn.commit()
    return {"day": day, "vdot": vdot, "source": source, "confidence": confidence}


def apply_event(conn, day: str, delta: float, reason: str,
                sessions: list[str] | None = None) -> dict | None:
    """Record a VDOT adjustment event. Returns the new state, or None if the
    weekly cap blocks it.
    """
    today = date.fromisoformat(day) if isinstance(day, str) else day
    last = conn.execute(
        "SELECT day FROM vdot_events ORDER BY id DESC LIMIT 1",
    ).fetchone()
    if last is not None:
        try:
            last_day = date.fromisoformat(last["day"])
            if (today - last_day) < timedelta(days=7):
                return None
        except ValueError:
            pass
    base = current(conn)
    base_vdot = base["vdot"] if base else 45.0
    new_vdot = max(20.0, min(90.0, base_vdot + delta))
    conn.execute(
        "INSERT INTO vdot_events (day, delta, reason, sessions_json) VALUES (?,?,?,?)",
        (today.isoformat(), delta, reason, json.dumps(sessions or [])),
    )
    return record(conn, today.isoformat(), new_vdot, "adjustment", 1.0)
