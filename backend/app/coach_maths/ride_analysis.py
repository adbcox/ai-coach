"""Per-activity analysis (scan_bike / scan_run / scan_swim / scan_strength).

Reads samples + laps and writes to `ride_metrics`, `time_in_zone`, `climbs`,
`mean_max_power`, `mean_max_pace`, `swim_splits`, `detected_intervals`.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Iterable

from .efficiency import ef_bike, ef_run
from .load import _load_thresholds, power_tss, rpe_tss, rtss, stss
from .sport import family_for


# ---------------------------- Core samples helpers ---------------------------


def _samples(conn, aid: int) -> list[dict]:
    rows = conn.execute(
        "SELECT t, hr, cadence, power, speed, alt, dist "
        "FROM samples WHERE activity_id = ? ORDER BY t", (aid,),
    ).fetchall()
    return [dict(r) for r in rows]


def rolling_mean(values: list[float | None], window_s: int, dt_s: float) -> list[float | None]:
    """Simple rolling mean over `window_s` seconds of 1-Hz samples (dt_s assumed uniform).

    Missing (None) samples are ignored in the sum/count; result is None until
    enough valid samples have accumulated.
    """
    n = len(values)
    out: list[float | None] = [None] * n
    if n == 0:
        return out
    window_n = max(1, int(round(window_s / dt_s)))
    rolling_sum = 0.0
    rolling_count = 0
    buf: list[float | None] = []
    for i, v in enumerate(values):
        buf.append(v)
        if v is not None:
            rolling_sum += v
            rolling_count += 1
        if len(buf) > window_n:
            old = buf.pop(0)
            if old is not None:
                rolling_sum -= old
                rolling_count -= 1
        if rolling_count > 0:
            out[i] = rolling_sum / rolling_count
    return out


def normalised_power(power_series: list[float | None]) -> float | None:
    """Coggan NP = (mean((P_30s)^4))^0.25 over the activity."""
    if not power_series:
        return None
    rolled = rolling_mean(power_series, window_s=30, dt_s=1.0)
    valid = [v for v in rolled if v is not None and v > 0]
    if len(valid) < 30:                    # need a meaningful window
        return None
    mean_p4 = sum(v ** 4 for v in valid) / len(valid)
    return mean_p4 ** 0.25


def mean_max_curve(values: list[float | None], windows: list[int]) -> dict[int, float | None]:
    """Mean-max over each window (seconds). Returns {window_s: best_mean_or_None}."""
    out: dict[int, float | None] = {}
    for w in windows:
        rolled = rolling_mean(values, window_s=w, dt_s=1.0)
        best = None
        for r in rolled:
            if r is None:
                continue
            if best is None or r > best:
                best = r
        out[w] = best
    return out


def mean_max_pace_curve(speed_m_s: list[float | None], windows: list[int]) -> dict[int, float | None]:
    """Fastest mean speed over each window. Returns {window_s: m/s or None}."""
    return mean_max_curve(speed_m_s, windows)


# ---------------------------- Climbs -----------------------------------------


def detect_climbs(dist_m: list[float | None], alt_m: list[float | None],
                  min_length_m: float = 500.0,
                  min_gradient_pct: float = 3.0) -> list[dict]:
    """Return climbs: contiguous stretches with avg gradient >= min_gradient_pct
    and length >= min_length_m. Uses dist+alt only; no GPS.

    Gradient is windowed over 100 m to smooth GPS/altitude noise.
    """
    n = min(len(dist_m), len(alt_m))
    climbs: list[dict] = []
    if n < 3:
        return climbs
    # find rising stretches
    in_climb = False
    start = 0
    start_alt = alt_m[0] if alt_m[0] is not None else 0.0
    start_dist = dist_m[0] if dist_m[0] is not None else 0.0
    for i in range(1, n):
        d0 = dist_m[i - 1]
        d1 = dist_m[i]
        a0 = alt_m[i - 1]
        a1 = alt_m[i]
        if d0 is None or d1 is None or a0 is None or a1 is None or d1 <= d0:
            continue
        slope = (a1 - a0) / max(1.0, (d1 - d0)) * 100.0
        if slope >= min_gradient_pct * 0.3:
            if not in_climb:
                in_climb = True
                start = i - 1
                start_alt = a0
                start_dist = d0
        else:
            if in_climb:
                end = i - 1
                length = (dist_m[end] or 0.0) - start_dist
                rise = (alt_m[end] or 0.0) - start_alt
                avg = (rise / length * 100.0) if length > 0 else 0.0
                if length >= min_length_m and avg >= min_gradient_pct:
                    climbs.append({
                        "start_offset_s": float(start),
                        "end_offset_s": float(end),
                        "length_m": length,
                        "avg_gradient": avg,
                        "max_gradient": avg,
                        "vam": (rise / max(1.0, (end - start)) * 3600.0),
                    })
                in_climb = False
    if in_climb:
        end = n - 1
        length = (dist_m[end] or 0.0) - start_dist
        rise = (alt_m[end] or 0.0) - start_alt
        avg = (rise / length * 100.0) if length > 0 else 0.0
        if length >= min_length_m and avg >= min_gradient_pct:
            climbs.append({
                "start_offset_s": float(start),
                "end_offset_s": float(end),
                "length_m": length,
                "avg_gradient": avg,
                "max_gradient": avg,
                "vam": (rise / max(1.0, (end - start)) * 3600.0),
            })
    return climbs


# ---------------------------- Zones ------------------------------------------


def hr_zones(max_hr: float, lthr: float | None) -> list[float]:
    """Return 5 upper-bounds (bpm) for HR zones. Classic Friel/Coggan split."""
    if lthr and lthr > 0:
        return [lthr * 0.80, lthr * 0.88, lthr * 0.94, lthr * 1.02, max(max_hr, lthr * 1.10)]
    return [max_hr * 0.60, max_hr * 0.70, max_hr * 0.80, max_hr * 0.90, max_hr]


def time_in_hr_zones(hr_series: list[int | None], zones: list[float]) -> dict[int, float]:
    out: dict[int, float] = {1: 0.0, 2: 0.0, 3: 0.0, 4: 0.0, 5: 0.0}
    for v in hr_series:
        if v is None or v <= 0:
            continue
        for i, upper in enumerate(zones, start=1):
            if v <= upper:
                out[i] += 1.0
                break
        else:
            out[5] += 1.0
    return out


# ---------------------------- Scanners ---------------------------------------


_MMP_WINDOWS = [5, 15, 30, 60, 120, 300, 600, 1200, 1800, 3600]


def scan_bike(conn, aid: int) -> dict:
    """Bike: NP, IF, TSS, hrTSS, EF, MMP curve, climbs, time-in-HR."""
    rows = _samples(conn, aid)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    act = conn.execute(
        "SELECT sport, duration_s, distance_m, avg_hr FROM activities WHERE id = ?",
        (aid,),
    ).fetchone()
    family = family_for(act["sport"])
    th = _load_thresholds(conn, act["sport"])
    power = [r["power"] for r in rows]
    hr = [r["hr"] for r in rows]
    alt = [r["alt"] for r in rows]
    dist = [r["dist"] for r in rows]
    np = normalised_power(power)
    tss, _ = power_tss(act["duration_s"] or 0.0, np, None, th["ftp"])
    if_ = (np / th["ftp"]) if (np and th["ftp"]) else None
    ef = ef_bike(np, act["avg_hr"])
    mmp = mean_max_curve(power, _MMP_WINDOWS)
    climbs = detect_climbs(dist, alt)
    pacing_cv = _cv([v for v in power if v is not None])
    _persist_ride_metrics(conn, aid, family, np=np, if_=if_, tss=tss, ef=ef,
                          pacing_cv=pacing_cv, ftp=th["ftp"], lthr=th["lthr"], now=now)
    _persist_mmp(conn, aid, mmp, pace=False)
    _persist_climbs(conn, aid, climbs)
    if act["avg_hr"] and th["max_hr"]:
        zones = hr_zones(th["max_hr"], th["lthr"])
        _persist_time_in_zone(conn, aid, "hr", time_in_hr_zones(hr, zones))
    conn.commit()
    return {"family": family, "np": np, "if": if_, "tss": tss, "ef": ef,
            "climbs": len(climbs), "mmp_samples": sum(1 for v in mmp.values() if v is not None)}


def scan_run(conn, aid: int) -> dict:
    """Run: rTSS, EF, MMP (pace), climbs, time-in-HR."""
    rows = _samples(conn, aid)
    now = datetime.now(UTC).isoformat(timespec="seconds")
    act = conn.execute(
        "SELECT sport, duration_s, distance_m, avg_hr FROM activities WHERE id = ?",
        (aid,),
    ).fetchone()
    family = family_for(act["sport"])
    th = _load_thresholds(conn, act["sport"])
    hr = [r["hr"] for r in rows]
    speed = [r["speed"] for r in rows]
    alt = [r["alt"] for r in rows]
    dist = [r["dist"] for r in rows]
    tss, _ = rtss(act["duration_s"] or 0.0, th["threshold_pace_s_per_m"],
                  act["distance_m"] or 0.0, act["avg_hr"])
    # NGP approximation: use mean speed; a true NGP would adjust for grade.
    mean_speed = (act["distance_m"] / act["duration_s"]) if (
        act["distance_m"] and act["duration_s"]) else None
    ef = ef_run(mean_speed, act["avg_hr"])
    mmp = mean_max_pace_curve(speed, _MMP_WINDOWS)
    climbs = detect_climbs(dist, alt)
    pacing_cv = _cv([v for v in speed if v is not None])
    _persist_ride_metrics(conn, aid, family, rtss_v=tss, ef=ef, pacing_cv=pacing_cv,
                          threshold_pace=th["threshold_pace_s_per_m"], lthr=th["lthr"], now=now)
    _persist_mmp(conn, aid, mmp, pace=True)
    _persist_climbs(conn, aid, climbs)
    if act["avg_hr"] and th["max_hr"]:
        zones = hr_zones(th["max_hr"], th["lthr"])
        _persist_time_in_zone(conn, aid, "hr", time_in_hr_zones(hr, zones))
    conn.commit()
    return {"family": family, "rtss": tss, "ef": ef, "climbs": len(climbs)}


def scan_swim(conn, aid: int) -> dict:
    """Swim: sTSS and per-lap splits (from laps)."""
    now = datetime.now(UTC).isoformat(timespec="seconds")
    act = conn.execute(
        "SELECT sport, duration_s, distance_m, avg_hr FROM activities WHERE id = ?",
        (aid,),
    ).fetchone()
    family = family_for(act["sport"])
    th = _load_thresholds(conn, act["sport"])
    tss, _ = stss(act["duration_s"] or 0.0, th["css_s_per_m"], act["distance_m"] or 0.0)
    laps = conn.execute(
        "SELECT idx, timer_s, distance_m, avg_speed, avg_cadence FROM laps "
        "WHERE activity_id = ? ORDER BY idx", (aid,),
    ).fetchall()
    conn.execute("DELETE FROM swim_splits WHERE activity_id = ?", (aid,))
    for lap in laps:
        if not lap["distance_m"] or lap["distance_m"] <= 0:
            continue
        strokes_per_min = lap["avg_cadence"]  # Garmin stores stroke rate as cadence
        strokes = int(((strokes_per_min or 0) / 60.0) * (lap["timer_s"] or 0.0))
        swolf = ((lap["timer_s"] or 0.0) + strokes) if lap["distance_m"] > 0 else None
        conn.execute(
            "INSERT INTO swim_splits (activity_id, idx, distance_m, time_s, strokes, swolf) "
            "VALUES (?,?,?,?,?,?)",
            (aid, lap["idx"], lap["distance_m"], lap["timer_s"], strokes, swolf),
        )
    _persist_ride_metrics(conn, aid, family, stss_v=tss, css=th["css_s_per_m"], now=now)
    conn.commit()
    return {"family": family, "stss": tss, "splits": len(laps)}


def scan_strength(conn, aid: int) -> dict:
    """Strength: rpeTSS from rpe stored in sync_state (manual) + HR peak."""
    now = datetime.now(UTC).isoformat(timespec="seconds")
    act = conn.execute(
        "SELECT sport, duration_s, avg_hr FROM activities WHERE id = ?", (aid,),
    ).fetchone()
    family = family_for(act["sport"])
    rpe_row = conn.execute(
        "SELECT value FROM sync_state WHERE key = ?", (f"rpe.{aid}",),
    ).fetchone()
    rpe = float(rpe_row["value"]) if rpe_row and rpe_row[0] else None
    tss, _ = rpe_tss(act["duration_s"] or 0.0, rpe)
    _persist_ride_metrics(conn, aid, family, rpetss_v=tss, now=now)
    conn.commit()
    return {"family": family, "rpetss": tss}


def scan_activity(conn, aid: int) -> dict:
    """Dispatch on family."""
    act = conn.execute(
        "SELECT sport FROM activities WHERE id = ?", (aid,),
    ).fetchone()
    if act is None:
        return {}
    family = family_for(act["sport"])
    if family in ("bike_road", "bike_indoor", "bike_trail"):
        return scan_bike(conn, aid)
    if family in ("run_road", "run_trail"):
        return scan_run(conn, aid)
    if family in ("swim_pool", "swim_open"):
        return scan_swim(conn, aid)
    if family == "strength":
        return scan_strength(conn, aid)
    return {"family": family}


class RideScanner:
    """Runs scan_activity() for activities that don't yet have a ride_metrics row.

    `start()` is fire-and-forget: it's idempotent and safe to call after every
    sync. We do it synchronously here (post-sync hook is already in a thread).
    """

    def __init__(self, settings) -> None:
        self.settings = settings

    def start(self) -> int:
        from .. import db
        conn = db.connect(self.settings.db_path)
        try:
            rows = conn.execute(
                "SELECT a.id FROM activities a "
                "LEFT JOIN ride_metrics r ON r.activity_id = a.id "
                "WHERE r.activity_id IS NULL ORDER BY a.start_time",
            ).fetchall()
            n = 0
            for r in rows:
                try:
                    scan_activity(conn, r["id"])
                    n += 1
                except Exception:   # a bad activity must never stop the batch
                    continue
            return n
        finally:
            conn.close()


# ---------------------------- Internals --------------------------------------


def _cv(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    if mean <= 0:
        return None
    var = sum((v - mean) ** 2 for v in values) / len(values)
    import math
    return math.sqrt(var) / mean


def _persist_ride_metrics(conn, aid: int, family: str, *,
                          np: float | None = None, if_: float | None = None,
                          tss: float | None = None, hrtss_v: float | None = None,
                          rtss_v: float | None = None, stss_v: float | None = None,
                          rpetss_v: float | None = None, ef: float | None = None,
                          pacing_cv: float | None = None, fade_pct: float | None = None,
                          decoupling_pct: float | None = None, ftp: float | None = None,
                          lthr: float | None = None, threshold_pace: float | None = None,
                          css: float | None = None, now: str) -> None:
    conn.execute(
        "INSERT INTO ride_metrics (activity_id, family, np, if_, tss, hrtss, rtss, stss, "
        "rpetss, ef, pacing_cv, fade_pct, decoupling_pct, ftp_at_time, lthr_at_time, "
        "threshold_pace_at_time, css_at_time, computed_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(activity_id) DO UPDATE SET family=excluded.family, np=excluded.np, "
        "if_=excluded.if_, tss=excluded.tss, hrtss=excluded.hrtss, rtss=excluded.rtss, "
        "stss=excluded.stss, rpetss=excluded.rpetss, ef=excluded.ef, "
        "pacing_cv=excluded.pacing_cv, fade_pct=excluded.fade_pct, "
        "decoupling_pct=excluded.decoupling_pct, ftp_at_time=excluded.ftp_at_time, "
        "lthr_at_time=excluded.lthr_at_time, threshold_pace_at_time=excluded.threshold_pace_at_time, "
        "css_at_time=excluded.css_at_time, computed_at=excluded.computed_at",
        (aid, family, np, if_, tss, hrtss_v, rtss_v, stss_v, rpetss_v, ef, pacing_cv,
         fade_pct, decoupling_pct, ftp, int(lthr) if lthr else None, threshold_pace, css, now),
    )


def _persist_mmp(conn, aid: int, curve: dict[int, float | None], *, pace: bool) -> None:
    table = "mean_max_pace" if pace else "mean_max_power"
    val_col = "metres_per_s" if pace else "watts"
    conn.execute(f"DELETE FROM {table} WHERE activity_id = ?", (aid,))
    for w, v in curve.items():
        if v is None:
            continue
        conn.execute(
            f"INSERT INTO {table} (activity_id, window_s, {val_col}) VALUES (?, ?, ?)",
            (aid, w, v),
        )


def _persist_climbs(conn, aid: int, climbs: list[dict]) -> None:
    conn.execute("DELETE FROM climbs WHERE activity_id = ?", (aid,))
    for i, c in enumerate(climbs):
        conn.execute(
            "INSERT INTO climbs (activity_id, idx, start_offset_s, end_offset_s, length_m, "
            "avg_gradient, max_gradient, vam) VALUES (?,?,?,?,?,?,?,?)",
            (aid, i, c["start_offset_s"], c["end_offset_s"], c["length_m"],
             c["avg_gradient"], c["max_gradient"], c["vam"]),
        )


def _persist_time_in_zone(conn, aid: int, axis: str, zones: dict[int, float]) -> None:
    conn.execute("DELETE FROM time_in_zone WHERE activity_id = ? AND axis = ?", (aid, axis))
    for zone, seconds in zones.items():
        if seconds <= 0:
            continue
        conn.execute(
            "INSERT INTO time_in_zone (activity_id, axis, zone, seconds) VALUES (?,?,?,?)",
            (aid, axis, zone, seconds),
        )
