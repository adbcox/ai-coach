"""Per-activity load computation + daily PMC (CTL/ATL/TSB) + ACWR.

Methods
-------
* **power_tss**  — bike with power + FTP. NP = 4th-root of mean of 30s
  rolling-mean power ^ 4; IF = NP / FTP; TSS = (IF^2 * duration_h * 100).
  See Coggan, _Training and Racing with a Power Meter_.
* **hrtss**      — Banister TRIMP-ish converted to a TSS-equivalent; uses
  weighted HR reserve so an easy hour ≈ 60 and threshold hour ≈ 100.
* **rtss**       — running TSS from pace/NGP vs threshold pace:
  TSS = (IF^2 * duration_h * 100) with IF = pace / threshold_pace.
* **stss**       — swim TSS: (swim_speed / CSS)^3 × duration_h × 100.
* **rpetss**     — strength TSS: RPE × minutes × 100/(7×60).
* **duration**   — low-weight fallback: duration_min × 0.5.

PMC (EWMA): CTL τ=42 (fitness, slow), ATL τ=7 (fatigue, fast),
TSB = CTL - ATL. Decayed forward one day at a time, warm-started from
the previous stored day if present (so recompute is cheap).

ACWR: acute (7d mean) / chronic (28d mean) daily TSS. Soft guide only (D5).
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from .sport import family_for, methods_for, seed_sport

# PMC time constants (classic Banister / TrainingPeaks values).
CTL_TAU = 42.0
ATL_TAU = 7.0


@dataclass
class LoadInput:
    activity_id: int
    sport_key: str | None
    duration_s: float
    distance_m: float
    avg_hr: float | None
    max_hr_user: float | None            # the user's max HR (preferences or Garmin's)
    ftp: float | None                    # Watts
    lthr: float | None                   # bpm
    threshold_pace_s_per_m: float | None # s/m (lower = faster); run threshold
    css_s_per_m: float | None            # s/m; swim critical speed
    avg_power: float | None              # Watts (fallback NP source)
    np: float | None                     # Watts, if already computed from samples
    rpe: float | None                    # strength 1-10
    source_name: str | None              # activity.name (used for "other" keywords)


# ------------------------------- TSS variants --------------------------------


def power_tss(duration_s: float, np: float | None, avg_power: float | None,
              ftp: float | None) -> tuple[float | None, dict]:
    """Returns (tss, inputs). Requires NP (or avg_power) + FTP."""
    if not ftp or ftp <= 0:
        return None, {"reason": "no-ftp"}
    norm = np if np and np > 0 else avg_power
    if not norm or norm <= 0 or duration_s <= 0:
        return None, {"reason": "no-power"}
    if_ = norm / ftp
    hours = duration_s / 3600.0
    tss = (if_ * if_) * hours * 100.0
    return tss, {"np": norm, "ftp": ftp, "if_": if_, "duration_s": duration_s}


def rtss(duration_s: float, threshold_pace_s_per_m: float | None,
         distance_m: float, avg_hr: float | None) -> tuple[float | None, dict]:
    """Running TSS from pace (s/m) vs threshold pace."""
    if not threshold_pace_s_per_m or threshold_pace_s_per_m <= 0:
        return None, {"reason": "no-threshold-pace"}
    if duration_s <= 0 or distance_m <= 0:
        return None, {"reason": "zero-time-or-distance"}
    pace = duration_s / distance_m  # s/m
    if pace <= 0:
        return None, {"reason": "bad-pace"}
    # IF = threshold / pace (lower s/m → faster → higher IF).
    if_ = threshold_pace_s_per_m / pace
    hours = duration_s / 3600.0
    tss = (if_ * if_) * hours * 100.0
    return tss, {"pace_s_per_m": pace, "threshold_s_per_m": threshold_pace_s_per_m,
                 "if_": if_, "duration_s": duration_s}


def stss(duration_s: float, css_s_per_m: float | None,
         distance_m: float) -> tuple[float | None, dict]:
    """Swim TSS: (swim_speed / CSS)^3 * duration_h * 100 with speed = m/s."""
    if not css_s_per_m or css_s_per_m <= 0:
        return None, {"reason": "no-css"}
    if duration_s <= 0 or distance_m <= 0:
        return None, {"reason": "zero-time-or-distance"}
    speed = distance_m / duration_s          # m/s
    css_speed = 1.0 / css_s_per_m            # m/s
    if speed <= 0 or css_speed <= 0:
        return None, {"reason": "bad-speed"}
    ratio = speed / css_speed
    hours = duration_s / 3600.0
    tss = (ratio ** 3) * hours * 100.0
    return tss, {"speed_m_s": speed, "css_speed_m_s": css_speed,
                 "duration_s": duration_s}


def rpe_tss(duration_s: float, rpe: float | None) -> tuple[float | None, dict]:
    """Strength TSS: RPE × minutes × k with k = 100 / (7 × 60) ≈ 0.238."""
    if rpe is None or rpe <= 0 or duration_s <= 0:
        return None, {"reason": "no-rpe"}
    k = 100.0 / (7.0 * 60.0)
    minutes = duration_s / 60.0
    tss = rpe * minutes * k
    return tss, {"rpe": rpe, "minutes": minutes, "k": k}


def hrtss(duration_s: float, avg_hr: float | None, lthr: float | None,
          max_hr: float | None) -> tuple[float | None, dict]:
    """HR-based TSS using Banister TRIMP weighted by HR reserve.

    HRR = (avg_hr - 60) / (max_hr - 60); weighted multiplier
    `1.92 * exp(1.92 * HRR)` is the men's curve (Banister 1991) scaled so
    a one-hour effort at LTHR equals ~100 TSS.
    """
    if not avg_hr or avg_hr <= 0 or duration_s <= 0:
        return None, {"reason": "no-hr"}
    if not max_hr or max_hr <= 60:
        return None, {"reason": "no-max-hr"}
    if not lthr or lthr <= 0:
        return None, {"reason": "no-lthr"}
    hrr = max(0.0, min(1.0, (avg_hr - 60.0) / (max_hr - 60.0)))
    lt_hrr = max(0.01, min(1.0, (lthr - 60.0) / (max_hr - 60.0)))
    # TRIMP (Banister) in minutes, then normalised so 1h at LTHR → 100.
    k = 1.92
    trimp_min = hrr * math.exp(k * hrr)
    trimp_lt_min = lt_hrr * math.exp(k * lt_hrr)
    minutes = duration_s / 60.0
    if trimp_lt_min <= 0:
        return None, {"reason": "bad-lthr"}
    tss = (trimp_min / trimp_lt_min) * (minutes / 60.0) * 100.0
    return tss, {"hrr": hrr, "lt_hrr": lt_hrr, "minutes": minutes,
                 "lthr": lthr, "max_hr": max_hr}


def duration_tss(duration_s: float) -> tuple[float, dict]:
    """Low-weight fallback when nothing else is available."""
    minutes = max(0.0, duration_s / 60.0)
    return minutes * 0.5, {"minutes": minutes}


# ------------------------- TRIMP (Banister, minutes) -------------------------


def trimp(duration_s: float, avg_hr: float | None, lthr: float | None,
          max_hr: float | None) -> float | None:
    """Banister TRIMP in minutes-equivalent (not normalised to LTHR hour).

    Returned so test_trimp.py can assert absolute TRIMP values; the maths is
    the same curve hrtss() uses internally.
    """
    if not avg_hr or not max_hr or max_hr <= 60 or duration_s <= 0:
        return None
    hrr = max(0.0, min(1.0, (avg_hr - 60.0) / (max_hr - 60.0)))
    k = 1.92
    return (duration_s / 60.0) * hrr * math.exp(k * hrr)


# ------------------------------ Dispatcher -----------------------------------


def compute_activity_load(li: LoadInput) -> tuple[str, str, float | None, float | None, dict]:
    """Return (family, method_used, trimp_value, tss, inputs)."""
    family = family_for(li.sport_key)
    primary, fallback = methods_for(family)
    tr = trimp(li.duration_s, li.avg_hr, li.lthr, li.max_hr_user)
    for method in (primary, fallback):
        if method is None:
            continue
        tss_val, inputs = _apply(method, li)
        if tss_val is not None:
            inputs["method"] = method
            return family, method, tr, tss_val, inputs
    # final fallback: duration
    tss_val, inputs = duration_tss(li.duration_s)
    inputs["method"] = "duration"
    return family, "duration", tr, tss_val, inputs


def _apply(method: str, li: LoadInput) -> tuple[float | None, dict]:
    if method == "power_tss":
        return power_tss(li.duration_s, li.np, li.avg_power, li.ftp)
    if method == "rtss":
        return rtss(li.duration_s, li.threshold_pace_s_per_m, li.distance_m, li.avg_hr)
    if method == "stss":
        return stss(li.duration_s, li.css_s_per_m, li.distance_m)
    if method == "rpetss":
        return rpe_tss(li.duration_s, li.rpe)
    if method == "hrtss":
        return hrtss(li.duration_s, li.avg_hr, li.lthr, li.max_hr_user)
    if method == "duration":
        v, inp = duration_tss(li.duration_s)
        return v, inp
    return None, {"reason": f"unknown-method:{method}"}


# ------------------------------ Thresholds -----------------------------------


def _load_thresholds(conn, sport_key: str | None) -> dict[str, float | None]:
    """Pull manual thresholds from sync_state (D1: manual truth). Keys follow
    the pattern 'thresholds.<family>.{ftp|lthr|threshold_pace|css|max_hr}'."""
    family = family_for(sport_key)
    out: dict[str, float | None] = {
        "ftp": None,
        "lthr": None,
        "threshold_pace_s_per_m": None,
        "css_s_per_m": None,
        "max_hr": None,
    }
    for name in ("ftp", "lthr", "threshold_pace_s_per_m", "css_s_per_m", "max_hr"):
        # Try family-scoped key first, then a generic key.
        for full in (f"thresholds.{family}.{name}", f"thresholds.{name}"):
            row = conn.execute(
                "SELECT value FROM sync_state WHERE key = ?", (full,),
            ).fetchone()
            if row is not None and row[0] not in (None, ""):
                try:
                    out[name] = float(row[0])
                    break
                except ValueError:
                    pass
    return out


# ------------------------------ PMC + ACWR -----------------------------------


def _ewma(prev: float | None, today: float, tau: float) -> float:
    """One-day forward EWMA step."""
    alpha = 1.0 - math.exp(-1.0 / tau)
    if prev is None:
        return today * alpha
    return prev + alpha * (today - prev)


def _day_range(start: date, end: date) -> Iterable[date]:
    cur = start
    while cur <= end:
        yield cur
        cur = cur + timedelta(days=1)


def _activity_day(start_time: str) -> str:
    """Treat each activity as happening on its local-start date. start_time is ISO."""
    # We don't carry a user tz yet — the activity table stores a local ISO
    # string from Garmin (e.g. "2026-10-30 14:00:00"). Just split on 'T' or ' '.
    s = start_time.replace("T", " ").split(" ", 1)[0]
    try:
        date.fromisoformat(s)
        return s
    except ValueError:
        return datetime.now(UTC).date().isoformat()


# ------------------------------ Top-level API --------------------------------


def _row_input(conn, row) -> LoadInput:
    th = _load_thresholds(conn, row["sport"])
    return LoadInput(
        activity_id=row["id"],
        sport_key=row["sport"],
        duration_s=row["duration_s"] or 0.0,
        distance_m=row["distance_m"] or 0.0,
        avg_hr=row["avg_hr"],
        max_hr_user=th["max_hr"],
        ftp=th["ftp"],
        lthr=th["lthr"],
        threshold_pace_s_per_m=th["threshold_pace_s_per_m"],
        css_s_per_m=th["css_s_per_m"],
        avg_power=None,
        np=None,
        rpe=None,
        source_name=row["name"],
    )


def recompute_activity(conn, activity_id: int) -> tuple[str, str, float | None, float | None]:
    """Compute and persist one activity's load. Returns (family, method, trimp, tss)."""
    row = conn.execute(
        "SELECT id, sport, name, duration_s, distance_m, avg_hr, max_hr, start_time "
        "FROM activities WHERE id = ?", (activity_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"activity {activity_id} not found")
    seed_sport(conn, row["sport"])
    li = _row_input(conn, row)
    family, method, tr, tss, inputs = compute_activity_load(li)
    conn.execute(
        "INSERT INTO activity_load (activity_id, family, trimp, tss, method, inputs_json, "
        "computed_at) VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(activity_id) DO UPDATE SET family=excluded.family, trimp=excluded.trimp, "
        "tss=excluded.tss, method=excluded.method, inputs_json=excluded.inputs_json, "
        "computed_at=excluded.computed_at",
        (activity_id, family, tr, tss, method, json.dumps(inputs),
         datetime.now(UTC).isoformat(timespec="seconds")),
    )
    return family, method, tr, tss


def recompute_training_load(conn, since_day: str | None = None) -> dict:
    """Rebuild activity_load for all activities, then roll it up into daily
    totals and per-family daily totals, with PMC + ACWR. since_day is advisory
    — PMC decays from zero if unset.
    """
    # 1) per-activity loads
    rows = conn.execute(
        "SELECT id FROM activities ORDER BY start_time",
    ).fetchall()
    for r in rows:
        recompute_activity(conn, r["id"])
    # 2) roll up per day + per (day, family)
    day_totals: dict[str, dict[str, float]] = {}
    fam_totals: dict[tuple[str, str], dict[str, float]] = {}
    for r in conn.execute(
        "SELECT a.start_time, al.family, al.trimp, al.tss "
        "FROM activity_load al JOIN activities a ON a.id = al.activity_id "
        "ORDER BY a.start_time",
    ):
        day = _activity_day(r["start_time"])
        t = r["trimp"] or 0.0
        s = r["tss"] or 0.0
        d = day_totals.setdefault(day, {"trimp": 0.0, "tss": 0.0})
        d["trimp"] += t
        d["tss"] += s
        key = (day, r["family"])
        f = fam_totals.setdefault(key, {"trimp": 0.0, "tss": 0.0})
        f["trimp"] += t
        f["tss"] += s
    # 3) PMC (decayed to today)
    all_days: list[date] = []
    if day_totals:
        start = date.fromisoformat(min(day_totals.keys()))
        end = max(date.fromisoformat(min(day_totals.keys())), date.today())
        all_days = list(_day_range(start, end))
    ctl_prev: float | None = None
    atl_prev: float | None = None
    daily_tss: dict[date, float] = {date.fromisoformat(k): v["tss"] for k, v in day_totals.items()}
    now_iso = datetime.now(UTC).isoformat(timespec="seconds")
    conn.execute("DELETE FROM training_load_day")
    conn.execute("DELETE FROM training_load_day_family")
    recent_tss: list[float] = []  # for ACWR
    for d in all_days:
        today_tss = daily_tss.get(d, 0.0)
        ctl_prev = _ewma(ctl_prev, today_tss, CTL_TAU)
        atl_prev = _ewma(atl_prev, today_tss, ATL_TAU)
        tsb = ctl_prev - atl_prev
        recent_tss.append(today_tss)
        acwr = _acwr(recent_tss)
        key = d.isoformat()
        tr = day_totals.get(key, {}).get("trimp", 0.0)
        ts = day_totals.get(key, {}).get("tss", 0.0)
        conn.execute(
            "INSERT INTO training_load_day (day, trimp, tss, ctl, atl, tsb, acwr, computed_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (key, tr, ts, ctl_prev, atl_prev, tsb, acwr, now_iso),
        )
    # per-family PMC
    families = sorted({fam for (_, fam) in fam_totals.keys()})
    for fam in families:
        ctl_p: float | None = None
        atl_p: float | None = None
        for d in all_days:
            today_tss = fam_totals.get((d.isoformat(), fam), {}).get("tss", 0.0)
            today_trimp = fam_totals.get((d.isoformat(), fam), {}).get("trimp", 0.0)
            ctl_p = _ewma(ctl_p, today_tss, CTL_TAU)
            atl_p = _ewma(atl_p, today_tss, ATL_TAU)
            conn.execute(
                "INSERT INTO training_load_day_family (day, family, trimp, tss, ctl, atl, tsb) "
                "VALUES (?,?,?,?,?,?,?)",
                (d.isoformat(), fam, today_trimp, today_tss, ctl_p, atl_p, ctl_p - atl_p),
            )
    conn.commit()
    return {"days": len(all_days), "activities": len(rows),
            "families": families}


def _acwr(recent: list[float]) -> float | None:
    """Soft-guide ACWR 7/28 from the end of `recent` (today inclusive).

    Returns None until we have >= 28 days of history; otherwise acute (7d
    mean) / chronic (28d mean), 0/0 → None.
    """
    if len(recent) < 28:
        return None
    acute = sum(recent[-7:]) / 7.0
    chronic = sum(recent[-28:]) / 28.0
    if chronic <= 0:
        return None
    return acute / chronic


def acwr_7_28(conn) -> float | None:
    """Current ACWR from training_load_day. None if < 28 days of history."""
    rows = conn.execute(
        "SELECT tss FROM training_load_day ORDER BY day",
    ).fetchall()
    if len(rows) < 28:
        return None
    tss = [r["tss"] or 0.0 for r in rows]
    return _acwr(tss)
