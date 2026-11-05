"""Daily workout suggestion engine.

Reads `routine_profile.latest`, picks a cluster that fits today's context,
and ranks candidates by a composite score. Readiness overrides act as
hard gates applied AFTER ranking so they can always force recovery when
Adrian is ill, red-banded, or dug deep yesterday.

Composite score (per spec §P2b.6 Stage B):
    S = 0.30·w1 + 0.30·w2 + 0.25·w3 + 0.15·w4
where
    w1 — weekday-family "usual" score (freq_on_weekday, this weekday)
    w2 — season-family match (duration/TSS ranges typical for the season)
    w3 — prelude signature match (prev 3d / 7d TSS and TSB align with the
         cluster's best-EF prelude)
    w4 — rhythm fit (slot in the dominant 52w H/E/- pattern)

Readiness overrides (hard, applied after ranking):
    * `checkin.ill == 1` → force short-recovery first; demote the rest.
    * `readiness.band == 'red'` → drop tempo/interval/VO2/race from the list.
    * `TSB < -20` → downgrade hard candidates by 40 %.
    * `last_1d_TSS` top 5 % AND `readiness < yesterday.readiness - 10`
      → cap at recovery / endurance-easy.

Sample-size guard: if `n_history < 20` for the weekday-family pair, we set
`low_confidence=true` on the response.
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from app.coach_maths import routine as _routine


_HARD_CLUSTERS = {"tempo medium", "interval hard", "VO2 hard", "race"}
_RECOVERY_CLUSTERS = {"short recovery"}
_EASY_CLUSTERS = {"short recovery", "endurance medium"}


# ---------------------------------------------------------------------------

@dataclass
class Candidate:
    family: str
    cluster: str
    centroid: dict          # duration_min, tss, decoupling_pct, has_intervals
    weekday_dist: list[float] = field(default_factory=list)
    w1: float = 0.0
    w2: float = 0.0
    w3: float = 0.0
    w4: float = 0.0
    n_history: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def score(self) -> float:
        return 0.30 * self.w1 + 0.30 * self.w2 + 0.25 * self.w3 + 0.15 * self.w4

    def as_dict(self) -> dict:
        return {
            "family": self.family,
            "cluster": self.cluster,
            "duration_min": round(self.centroid["duration_min"], 1),
            "tss": round(self.centroid["tss"], 1),
            "decoupling_pct": round(self.centroid["decoupling_pct"], 1),
            "has_intervals": bool(self.centroid["has_intervals"] >= 0.5),
            "score": round(self.score, 3),
            "components": {
                "w1_weekday": round(self.w1, 3),
                "w2_season": round(self.w2, 3),
                "w3_prelude": round(self.w3, 3),
                "w4_rhythm": round(self.w4, 3),
            },
            "n_history": self.n_history,
            "notes": self.notes,
        }


# ---- scorer helpers ------------------------------------------------------

def _weekday_fit(profile: dict, cand: Candidate, weekday: int) -> tuple[float, int]:
    """Return (w1, n_history). Prefers 90d, falls back to 365d then all.

    Combines weekday-family frequency, centroid-duration similarity, AND the
    cluster's own weekday share so a Tuesday-tempo doesn't lose out to a
    Thursday-recovery cluster that also happens to be a "usual" ride.
    """
    for window in ("90d", "365d", "all"):
        block = profile.get("by_weekday_family", {}).get(window, {})
        row = block.get(f"{weekday}:{cand.family}")
        if row and row.get("duration_min", {}).get("n"):
            n = row["duration_min"]["n"]
            freq = row.get("freq_on_weekday", 0.0)
            dur_p50 = row["duration_min"].get("p50") or 0.0
            sim = 1.0 - min(1.0, abs(dur_p50 - cand.centroid["duration_min"]) / max(dur_p50, 1.0))
            cluster_share = cand.weekday_dist[weekday] if cand.weekday_dist and weekday < len(cand.weekday_dist) else 0.0
            return freq * 0.3 + sim * 0.3 + cluster_share * 0.4, n
    return 0.0, 0


def _season_fit(profile: dict, cand: Candidate, today: date) -> float:
    """Candidate is "in season" if its duration lies between p50 and p90 of
    the family's seasonal distribution. We only penalise candidates that
    extend well past p90 (way longer than usual for this season)."""
    season = _routine._SEASONS[today.month]
    row = profile.get("by_season_family", {}).get(f"{season}:{cand.family}")
    if not row:
        return 0.5
    dur_p90 = row.get("duration_min", {}).get("p90") or 0.0
    if dur_p90 <= 0:
        return 0.5
    if cand.centroid["duration_min"] <= dur_p90:
        return 1.0
    excess = (cand.centroid["duration_min"] - dur_p90) / dur_p90
    return max(0.0, 1.0 - excess)


def _prelude_fit(profile: dict, cand: Candidate, prev_3d_tss: float,
                 prev_7d_tss: float, prev_3d_tsb: float | None) -> float:
    sig = profile.get("prelude_signatures", {}).get(cand.family)
    if not sig:
        return 0.0
    t3 = sig.get("prev_3d_tss_mean") or 0.0
    t7 = sig.get("prev_7d_tss_mean") or 0.0
    s1 = 1.0 - min(1.0, abs(t3 - prev_3d_tss) / max(t3, 50.0))
    s2 = 1.0 - min(1.0, abs(t7 - prev_7d_tss) / max(t7, 150.0))
    if prev_3d_tsb is not None and sig.get("prev_3d_tsb_mean") is not None:
        tsb_sig = sig["prev_3d_tsb_mean"]
        s3 = 1.0 - min(1.0, abs(tsb_sig - prev_3d_tsb) / 25.0)
    else:
        s3 = 0.5
    return (s1 + s2 + s3) / 3.0


def _rhythm_fit(profile: dict, cand: Candidate, weekday: int) -> float:
    rhythm = profile.get("weekly_rhythm", {})
    patterns = rhythm.get("patterns") or []
    if not patterns:
        return 0.5
    # First (most common) pattern dominates.
    top = patterns[0]["pattern"]
    if weekday >= len(top):
        return 0.5
    slot = top[weekday]
    if slot == "H":
        return 1.0 if cand.cluster in _HARD_CLUSTERS or cand.centroid["tss"] >= 90 else 0.3
    if slot == "E":
        return 1.0 if cand.cluster not in _HARD_CLUSTERS else 0.4
    return 0.7 if cand.cluster in _RECOVERY_CLUSTERS else 0.4  # rest-day slot


# ---- today context --------------------------------------------------------

def _prev_tss(conn: sqlite3.Connection, today: date) -> tuple[float, float]:
    rows = conn.execute(
        "SELECT day, tss FROM training_load_day WHERE day < ? AND day >= ? AND tss IS NOT NULL",
        (today.isoformat(), (today - timedelta(days=7)).isoformat()),
    ).fetchall()
    tss_by_day = {r["day"]: float(r["tss"] or 0.0) for r in rows}
    prev_3 = sum(tss_by_day.get((today - timedelta(days=i)).isoformat(), 0.0) for i in range(1, 4))
    prev_7 = sum(tss_by_day.get((today - timedelta(days=i)).isoformat(), 0.0) for i in range(1, 8))
    return prev_3, prev_7


def _prev_tsb(conn: sqlite3.Connection, today: date) -> float | None:
    row = conn.execute(
        "SELECT tsb FROM training_load_day WHERE day < ? ORDER BY day DESC LIMIT 1",
        (today.isoformat(),),
    ).fetchone()
    if row is None or row["tsb"] is None:
        return None
    return float(row["tsb"])


def _readiness_today(conn: sqlite3.Connection, today: date) -> tuple[int | None, str | None]:
    row = conn.execute(
        "SELECT score, band FROM readiness_day WHERE day = ?",
        (today.isoformat(),),
    ).fetchone()
    if row is None:
        return None, None
    return row["score"], row["band"]


def _ill_today(conn: sqlite3.Connection, today: date) -> bool:
    row = conn.execute(
        "SELECT ill FROM checkins WHERE day = ?", (today.isoformat(),),
    ).fetchone()
    if row is None:
        return False
    try:
        return bool(row["ill"])
    except (IndexError, KeyError):
        return False


def _p95_last_30d_tss(conn: sqlite3.Connection, today: date) -> float | None:
    rows = conn.execute(
        "SELECT tss FROM training_load_day WHERE day >= ? AND day < ? AND tss IS NOT NULL",
        ((today - timedelta(days=30)).isoformat(), today.isoformat()),
    ).fetchall()
    tss = [float(r["tss"]) for r in rows if r["tss"] is not None]
    if len(tss) < 10:
        return None
    s = sorted(tss)
    idx = max(0, min(len(s) - 1, int(round(0.95 * (len(s) - 1)))))
    return s[idx]


# ---- overrides ------------------------------------------------------------

def _apply_overrides(candidates: list[Candidate], *,
                     ill: bool, band: str | None, tsb: float | None,
                     last_day_tss: float, p95_tss: float | None,
                     readiness_delta: int | None) -> list[Candidate]:
    pool = list(candidates)
    if ill:
        rec = [c for c in pool if c.cluster in _RECOVERY_CLUSTERS]
        if rec:
            for c in rec:
                c.notes.append("ill: forced to short-recovery")
            others = [c for c in pool if c not in rec]
            return rec + others  # recovery first, others demoted but kept
    if band == "red":
        before = len(pool)
        pool = [c for c in pool if c.cluster not in _HARD_CLUSTERS]
        for c in pool:
            c.notes.append("red band: hard removed")
        if before and not pool:
            return []
    if tsb is not None and tsb < -20:
        for c in pool:
            if c.cluster in _HARD_CLUSTERS:
                c.w1 *= 0.6
                c.w2 *= 0.6
                c.w3 *= 0.6
                c.w4 *= 0.6
                c.notes.append(f"tsb {tsb:.0f}: hard candidate downgraded 40%")
    if p95_tss is not None and last_day_tss >= p95_tss and readiness_delta is not None and readiness_delta < -10:
        pool = [c for c in pool if c.cluster in _EASY_CLUSTERS]
        for c in pool:
            c.notes.append("deep yesterday + readiness drop: capped at easy")
    return sorted(pool, key=lambda c: c.score, reverse=True)


# ---- top-level entry ------------------------------------------------------

def _readiness_delta(conn: sqlite3.Connection, today: date) -> int | None:
    rows = conn.execute(
        "SELECT day, score FROM readiness_day WHERE day <= ? ORDER BY day DESC LIMIT 2",
        (today.isoformat(),),
    ).fetchall()
    if len(rows) < 2 or rows[0]["score"] is None or rows[1]["score"] is None:
        return None
    return int(rows[0]["score"]) - int(rows[1]["score"])


def suggest_today(conn: sqlite3.Connection, today: date | None = None) -> dict:
    today = today or date.today()
    latest = _routine.latest(conn)
    if latest is None:
        return {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "day": today.isoformat(), "primary": None, "alternative": None,
                "candidates": [], "low_confidence": True,
                "reason": "no routine_profile row yet"}
    profile = latest["profile"]
    weekday = today.weekday()

    candidates: list[Candidate] = []
    for family, clusters in (profile.get("recurring_sessions") or {}).items():
        for cluster in clusters:
            cand = Candidate(
                family=family,
                cluster=cluster["cluster"],
                centroid=cluster["centroid"],
                weekday_dist=cluster.get("weekday_dist") or [],
            )
            cand.w1, cand.n_history = _weekday_fit(profile, cand, weekday)
            cand.w2 = _season_fit(profile, cand, today)
            prev3, prev7 = _prev_tss(conn, today)
            tsb_prev = _prev_tsb(conn, today)
            cand.w3 = _prelude_fit(profile, cand, prev3, prev7, tsb_prev)
            cand.w4 = _rhythm_fit(profile, cand, weekday)
            candidates.append(cand)

    ranked = sorted(candidates, key=lambda c: c.score, reverse=True)
    score_today, band = _readiness_today(conn, today)
    ill = _ill_today(conn, today)
    tsb_prev = _prev_tsb(conn, today)
    prev3, _prev7 = _prev_tss(conn, today)
    last_day_tss = sum(float(r["tss"] or 0.0) for r in conn.execute(
        "SELECT tss FROM training_load_day WHERE day = ?",
        ((today - timedelta(days=1)).isoformat(),),
    ).fetchall())
    p95 = _p95_last_30d_tss(conn, today)
    delta = _readiness_delta(conn, today)
    ranked = _apply_overrides(ranked, ill=ill, band=band, tsb=tsb_prev,
                              last_day_tss=last_day_tss, p95_tss=p95,
                              readiness_delta=delta)

    primary = ranked[0].as_dict() if ranked else None
    alternative = ranked[1].as_dict() if len(ranked) >= 2 else None
    low_conf = bool(ranked and ranked[0].n_history < 20)
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "day": today.isoformat(),
        "primary": primary,
        "alternative": alternative,
        "candidates": [c.as_dict() for c in ranked[:5]],
        "low_confidence": low_conf,
        "context": {
            "readiness": score_today,
            "band": band,
            "ill": ill,
            "tsb_prev": tsb_prev,
            "last_day_tss": last_day_tss,
            "p95_tss_30d": p95,
            "readiness_delta": delta,
        },
    }


def write_suggestion(conn: sqlite3.Connection, suggestion: dict) -> int:
    cur = conn.execute(
        "INSERT INTO suggestion_history (day, generated_at, primary_json, "
        "alternative_json) VALUES (?, ?, ?, ?)",
        (suggestion["day"], suggestion["generated_at"],
         json.dumps(suggestion.get("primary")),
         json.dumps(suggestion.get("alternative"))),
    )
    conn.commit()
    return int(cur.lastrowid)


def record_feedback(conn: sqlite3.Connection, sid: int, user_action: str) -> None:
    """user_action ∈ {did_it, swapped, ignored}. Idempotent per row."""
    if user_action not in {"did_it", "swapped", "ignored"}:
        raise ValueError("user_action must be did_it|swapped|ignored")
    conn.execute(
        "UPDATE suggestion_history SET user_action = ?, "
        "recorded_at = ? WHERE id = ?",
        (user_action, datetime.now(UTC).isoformat(timespec="seconds"), sid),
    )
    conn.commit()


def match_actual(conn: sqlite3.Connection, day: date) -> int:
    """For every suggestion on `day` with no actual_activity_id yet, pick the
    closest activity by cluster-centroid duration/TSS. Returns rows updated."""
    rows = conn.execute(
        "SELECT id, primary_json FROM suggestion_history "
        "WHERE day = ? AND actual_activity_id IS NULL AND primary_json IS NOT NULL",
        (day.isoformat(),),
    ).fetchall()
    if not rows:
        return 0
    acts = conn.execute(
        "SELECT a.id, a.duration_s, al.tss FROM activities a "
        "LEFT JOIN activity_load al ON al.activity_id = a.id "
        "WHERE date(a.start_time) = ?",
        (day.isoformat(),),
    ).fetchall()
    if not acts:
        return 0
    updated = 0
    for r in rows:
        try:
            primary = json.loads(r["primary_json"]) if r["primary_json"] else None
        except (TypeError, ValueError):
            continue
        if not primary:
            continue
        target_dur = primary.get("duration_min", 0.0)
        target_tss = primary.get("tss", 0.0)
        best_aid, best_sim = None, -1.0
        for act in acts:
            dur_min = float(act["duration_s"] or 0) / 60.0
            tss = float(act["tss"] or 0)
            dur_sim = 1.0 - min(1.0, abs(dur_min - target_dur) / max(target_dur, 1.0))
            tss_sim = 1.0 - min(1.0, abs(tss - target_tss) / max(target_tss, 1.0))
            sim = 0.5 * dur_sim + 0.5 * tss_sim
            if sim > best_sim:
                best_sim, best_aid = sim, int(act["id"])
        if best_aid is not None:
            conn.execute(
                "UPDATE suggestion_history SET actual_activity_id = ?, "
                "actual_similarity = ? WHERE id = ?",
                (best_aid, best_sim, r["id"]),
            )
            updated += 1
    conn.commit()
    return updated
