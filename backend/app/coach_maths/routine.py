"""Learn Adrian's training routine from all history.

Nightly job writes one `routine_profile` row with a JSON blob containing:
  - by_weekday_family: per (weekday 0-6, family) stats over 365d/90d/all.
  - by_season_family:  per (meteorological-season, family) stats over all.
  - weekly_rhythm:     for the last 52 weeks, hard/easy classification per day
                       and the dominant repeating weekly pattern.
  - recurring_sessions: per family, K-means (k=6) cluster centroids over
                       (duration, TSS, decoupling, has_intervals).
  - long_session_day:  weekday most often holding the weekly-max duration.
  - prelude_signatures: for each best-EF activity (top 10% within family),
                       what the previous 3 and 7 days looked like.

K-means is hand-rolled (no sklearn) — the dataset is a few thousand points
of four features, more than sufficient.
"""

from __future__ import annotations

import json
import random
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta


# ---- helpers -----------------------------------------------------------------

_SEASONS = {12: "DJF", 1: "DJF", 2: "DJF",
            3: "MAM", 4: "MAM", 5: "MAM",
            6: "JJA", 7: "JJA", 8: "JJA",
            9: "SON", 10: "SON", 11: "SON"}


def _pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(round(p * (len(s) - 1)))))
    return s[idx]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "mean": sum(values) / len(values),
        "p50": _pct(values, 0.5),
        "p90": _pct(values, 0.9),
    }


# ---- weekday / season --------------------------------------------------------

def _by_weekday_family(rows: list[sqlite3.Row], within_days: int | None,
                       today: date) -> dict:
    cutoff = None if within_days is None else today - timedelta(days=within_days)
    out: dict[str, dict] = {}
    buckets_dur: dict[tuple[int, str], list[float]] = defaultdict(list)
    buckets_tss: dict[tuple[int, str], list[float]] = defaultdict(list)
    weekday_totals: Counter = Counter()
    for r in rows:
        if r["family"] is None:
            continue
        d = _as_date(r["start_time"])
        if d is None:
            continue
        if cutoff is not None and d < cutoff:
            continue
        weekday_totals[d.weekday()] += 1
        key = (d.weekday(), r["family"])
        if r["duration_s"] is not None:
            buckets_dur[key].append(float(r["duration_s"]) / 60.0)  # minutes
        if r["tss"] is not None:
            buckets_tss[key].append(float(r["tss"]))
    for key, dur in buckets_dur.items():
        wd, fam = key
        tss = buckets_tss.get(key, [])
        total = weekday_totals.get(wd, 0) or 1
        out[f"{wd}:{fam}"] = {
            "weekday": wd,
            "family": fam,
            "count": len(dur),
            "freq_on_weekday": len(dur) / total,
            "duration_min": _stats(dur),
            "tss": _stats(tss),
            "usual": len(dur) / total >= 0.30,
        }
    return out


def _by_season_family(rows: list[sqlite3.Row]) -> dict:
    out: dict[str, dict] = {}
    buckets_dur: dict[tuple[str, str], list[float]] = defaultdict(list)
    buckets_tss: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in rows:
        d = _as_date(r["start_time"])
        if d is None or r["family"] is None:
            continue
        key = (_SEASONS[d.month], r["family"])
        if r["duration_s"] is not None:
            buckets_dur[key].append(float(r["duration_s"]) / 60.0)
        if r["tss"] is not None:
            buckets_tss[key].append(float(r["tss"]))
    for key, dur in buckets_dur.items():
        season, fam = key
        tss = buckets_tss.get(key, [])
        out[f"{season}:{fam}"] = {
            "season": season,
            "family": fam,
            "duration_min": _stats(dur),
            "tss": _stats(tss),
        }
    return out


# ---- weekly rhythm -----------------------------------------------------------

def _weekly_rhythm(conn: sqlite3.Connection, today: date) -> dict:
    """Classify each of the last 52 weeks as a 7-slot hard/easy string.
    Return the top 3 patterns."""
    tss_90 = [row["tss"] for row in conn.execute(
        "SELECT tss FROM training_load_day WHERE day >= ? AND tss IS NOT NULL",
        ((today - timedelta(days=90)).isoformat(),),
    ) if row["tss"] is not None]
    if len(tss_90) < 14:
        return {"patterns": [], "p70": None}
    p70 = _pct(tss_90, 0.7) or 0.0
    series = {row["day"]: row["tss"] for row in conn.execute(
        "SELECT day, tss FROM training_load_day WHERE day >= ? AND day <= ?",
        ((today - timedelta(days=52 * 7)).isoformat(), today.isoformat()),
    ) if row["tss"] is not None}
    patterns: Counter = Counter()
    for w in range(52):
        week_start = today - timedelta(days=(w + 1) * 7 - 1)
        slots: list[str] = []
        for i in range(7):
            day = (week_start + timedelta(days=i)).isoformat()
            tss = series.get(day, 0.0)
            slots.append("H" if tss > p70 else ("E" if tss > 0 else "-"))
        patterns["".join(slots)] += 1
    top = patterns.most_common(3)
    return {"p70": p70, "patterns": [{"pattern": p, "weeks": n} for p, n in top]}


# ---- recurring sessions (hand-rolled K-means) --------------------------------

@dataclass
class Session:
    aid: int
    family: str
    duration_min: float
    tss: float
    decoupling: float
    has_intervals: float
    weekday: int


def _collect_sessions(rows: list[sqlite3.Row]) -> list[Session]:
    out: list[Session] = []
    for r in rows:
        if r["family"] is None or r["duration_s"] is None:
            continue
        d = _as_date(r["start_time"])
        if d is None:
            continue
        out.append(Session(
            aid=r["activity_id"],
            family=r["family"],
            duration_min=float(r["duration_s"]) / 60.0,
            tss=float(r["tss"] or 0.0),
            decoupling=float(r["decoupling_pct"] or 0.0),
            has_intervals=1.0 if r["intervals_present"] else 0.0,
            weekday=d.weekday(),
        ))
    return out


def _kmeans(points: list[list[float]], k: int, *,
            iters: int = 25, seed: int = 0) -> tuple[list[list[float]], list[int]]:
    """Return (centroids, assignments). Simple Lloyd's algorithm with
    k-means++ init. Works on small point counts; good enough here."""
    rng = random.Random(seed)
    n = len(points)
    if n == 0:
        return [], []
    if n <= k:
        return [list(p) for p in points], list(range(n))
    # k-means++ initialisation.
    centroids = [points[rng.randrange(n)][:]]
    for _ in range(1, k):
        dists = [min(_sq_dist(p, c) for c in centroids) for p in points]
        s = sum(dists) or 1.0
        pick = rng.random() * s
        running = 0.0
        for i, d in enumerate(dists):
            running += d
            if running >= pick:
                centroids.append(points[i][:])
                break
    assignments = [0] * n
    for _ in range(iters):
        new_assign = []
        for p in points:
            best, best_d = 0, float("inf")
            for i, c in enumerate(centroids):
                d = _sq_dist(p, c)
                if d < best_d:
                    best, best_d = i, d
            new_assign.append(best)
        if new_assign == assignments:
            break
        assignments = new_assign
        for i in range(k):
            members = [points[j] for j, a in enumerate(assignments) if a == i]
            if members:
                centroids[i] = [sum(col) / len(col) for col in zip(*members, strict=False)]
    return centroids, assignments


def _sq_dist(a: list[float], b: list[float]) -> float:
    return sum((x - y) ** 2 for x, y in zip(a, b, strict=False))


def _name_cluster(centroid: list[float]) -> str:
    """Centroid order: [duration_min, tss, decoupling, has_intervals]."""
    dur, tss, dec, has_int = centroid
    if has_int >= 0.5 and tss >= 90:
        return "interval hard" if tss >= 120 else "tempo medium"
    if dur >= 150 and tss >= 150:
        return "endurance long"
    if dur <= 45 and tss <= 40:
        return "short recovery"
    if dur <= 75:
        return "endurance medium"
    return "endurance long"


def _recurring_sessions(rows: list[sqlite3.Row]) -> dict:
    sessions = _collect_sessions(rows)
    out: dict[str, list[dict]] = {}
    for family in sorted({s.family for s in sessions}):
        fam_sessions = [s for s in sessions if s.family == family]
        pts = [[s.duration_min, s.tss, s.decoupling, s.has_intervals]
               for s in fam_sessions]
        if len(pts) < 6:
            continue
        k = min(6, max(2, len(pts) // 10 + 1))
        centroids, assignments = _kmeans(pts, k)
        groups: dict[int, list[int]] = defaultdict(list)
        for i, a in enumerate(assignments):
            groups[a].append(i)
        clusters = []
        for cluster_id, members in groups.items():
            if cluster_id >= len(centroids):
                continue
            c = centroids[cluster_id]
            wd_counts = [0] * 7
            for m in members:
                wd_counts[fam_sessions[m].weekday] += 1
            total = sum(wd_counts) or 1
            weekday_dist = [round(c / total, 3) for c in wd_counts]
            clusters.append({
                "cluster": _name_cluster(c),
                "centroid": {
                    "duration_min": c[0],
                    "tss": c[1],
                    "decoupling_pct": c[2],
                    "has_intervals": c[3],
                },
                "n": len(members),
                "weekday_dist": weekday_dist,
            })
        out[family] = clusters
    return out


def _long_session_day(rows: list[sqlite3.Row], today: date) -> dict:
    """Weekday most often holding the max-duration activity of a week."""
    by_week: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for r in rows:
        d = _as_date(r["start_time"])
        if d is None or r["duration_s"] is None:
            continue
        key = f"{d.isocalendar().year}-{d.isocalendar().week:02d}"
        by_week[key].append((d, float(r["duration_s"])))
    weekday_counts: Counter = Counter()
    for week, items in by_week.items():
        items.sort(key=lambda x: x[1], reverse=True)
        weekday_counts[items[0][0].weekday()] += 1
    if not weekday_counts:
        return {"weekday": None, "count": 0}
    weekday, count = weekday_counts.most_common(1)[0]
    return {"weekday": weekday, "count": count}


# ---- prelude signatures ------------------------------------------------------

def _prelude_signatures(conn: sqlite3.Connection, rows: list[sqlite3.Row]) -> dict:
    """For the top 10 % EF rides per family, what did the previous 3 and
    7 days look like?"""
    by_family: dict[str, list[tuple[date, float]]] = defaultdict(list)
    for r in rows:
        d = _as_date(r["start_time"])
        if d is None or r["ef"] is None or r["family"] is None:
            continue
        by_family[r["family"]].append((d, float(r["ef"])))
    out: dict[str, dict] = {}
    pmc_rows = {r["day"]: (r["tss"], r["tsb"]) for r in conn.execute(
        "SELECT day, tss, tsb FROM training_load_day"
    )}
    for family, items in by_family.items():
        if len(items) < 20:
            continue
        items.sort(key=lambda x: x[1], reverse=True)
        top_n = max(2, len(items) // 10)
        tss_3 = []
        tss_7 = []
        tsb_3 = []
        for d, _ef in items[:top_n]:
            tss_sum_3, tss_sum_7, tsb_last = 0.0, 0.0, None
            for i in range(1, 8):
                dayk = (d - timedelta(days=i)).isoformat()
                pmc = pmc_rows.get(dayk)
                if pmc is None:
                    continue
                tss_sum_7 += pmc[0] or 0.0
                if i <= 3:
                    tss_sum_3 += pmc[0] or 0.0
                    if pmc[1] is not None:
                        tsb_last = pmc[1]
            tss_3.append(tss_sum_3)
            tss_7.append(tss_sum_7)
            if tsb_last is not None:
                tsb_3.append(tsb_last)
        out[family] = {
            "n_best": len(items[:top_n]),
            "prev_3d_tss_mean": sum(tss_3) / len(tss_3) if tss_3 else None,
            "prev_7d_tss_mean": sum(tss_7) / len(tss_7) if tss_7 else None,
            "prev_3d_tsb_mean": sum(tsb_3) / len(tsb_3) if tsb_3 else None,
        }
    return out


# ---- top-level entry point ---------------------------------------------------

def _as_date(iso: str | None) -> date | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).date()
    except ValueError:
        return None


def _detect_intervals(conn: sqlite3.Connection, aid: int) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM detected_intervals WHERE activity_id = ?", (aid,),
    ).fetchone()
    return (row["n"] if row else 0) > 0


def recompute_profile(conn: sqlite3.Connection, today: date | None = None) -> int:
    """Rebuild the routine profile. Returns the new row id."""
    today = today or date.today()
    rows = conn.execute(
        "SELECT a.id AS activity_id, a.start_time, "
        "       al.family, a.duration_s, al.tss, "
        "       rm.decoupling_pct, rm.ef, "
        "       EXISTS (SELECT 1 FROM detected_intervals di "
        "               WHERE di.activity_id = a.id) AS intervals_present "
        "FROM activities a "
        "LEFT JOIN activity_load al ON al.activity_id = a.id "
        "LEFT JOIN ride_metrics rm ON rm.activity_id = a.id "
        "ORDER BY a.start_time",
    ).fetchall()
    profile = {
        "by_weekday_family": {
            "365d": _by_weekday_family(rows, 365, today),
            "90d": _by_weekday_family(rows, 90, today),
            "all": _by_weekday_family(rows, None, today),
        },
        "by_season_family": _by_season_family(rows),
        "weekly_rhythm": _weekly_rhythm(conn, today),
        "recurring_sessions": _recurring_sessions(rows),
        "long_session_day": _long_session_day(rows, today),
        "prelude_signatures": _prelude_signatures(conn, rows),
    }
    cur = conn.execute(
        "INSERT INTO routine_profile (computed_at, profile_json) VALUES (?, ?)",
        (_now_iso(), json.dumps(profile)),
    )
    conn.commit()
    return int(cur.lastrowid)


def latest(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute(
        "SELECT id, computed_at, profile_json FROM routine_profile "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    try:
        profile = json.loads(row["profile_json"])
    except (TypeError, ValueError):
        return None
    return {"id": row["id"], "computed_at": row["computed_at"], "profile": profile}
