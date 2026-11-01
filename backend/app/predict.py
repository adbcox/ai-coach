"""Race time predictions that show their working.

Everything here is plain arithmetic on the athlete's own best efforts. Each method
returns the numbers it used and a list of human-readable steps ("the math"), so the
UI, an exported file and any AI agent all see exactly the same calculation.
"""

from __future__ import annotations

import math
import sqlite3
from datetime import UTC, datetime, timedelta
from statistics import median
from typing import Any

from . import references
from .efforts import DISTANCES, HALF, MARATHON, cost_ratio, minetti_cost, run_kind

TARGETS = [("5k", "5K", 5000.0), ("10k", "10K", 10000.0), ("half", "Half marathon", HALF),
           ("marathon", "Marathon", MARATHON)]
RIEGEL_MIN_S = 3.5 * 60    # Riegel 1981 Table 1: running records 1.5-42.2 km = 3.5-129 min (men), 3.9-147 min (women)
RIEGEL_MAX_S = 230 * 60    # app rule: wider than the paper's record times so slower recreational marathons count
CS_MIN_S, CS_MAX_S = 2 * 60, 30 * 60  # Poole 2016: CP fitted from 2-15 min efforts; above-CP exercise lasts 'perhaps 30 minutes' at most
MAX_SPEED = 7.0
T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262,
        10: 2.228, 12: 2.179, 15: 2.131, 20: 2.086, 30: 2.042}

CITATION_IDS = ["riegel1981", "daniels1979", "poole2016", "minetti2002", "fetch_everyone", "valencia2025", "latorre2025", "kasiak2023"]

CAVEATS = [
    "These are estimates built from your best efforts. A best effort inside a training run is not an "
    "all-out race, so predictions from them tend to be optimistic; a real race also depends on pacing, "
    "weather, course, nutrition, taper and the day.",
    "Predictions are least reliable for distances much longer than the efforts they come from. The "
    "marathon in particular depends on endurance training (weekly distance, long runs) that a 5K or 10K "
    "time does not capture. No endurance adjustment is applied; your recent training is shown beside the "
    "result so you can judge it.",
    "Not medical advice. Do not use a predicted time to push through pain, illness or injury.",
]


# ---------------------------------------------------------------- formatting
def fmt_time(s: float) -> str:
    s = round(s)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"


def fmt_pace(sec_per_km: float) -> str:
    s = round(sec_per_km)
    return f"{s // 60}:{s % 60:02d}/km"


def km(d: float) -> str:
    return f"{d / 1000:.4g} km" if d != 21097.5 else "21.0975 km"


# ---------------------------------------------------------------- models
def riegel(t1: float, d1: float, d2: float, k: float = 1.06) -> float:
    return t1 * (d2 / d1) ** k


def vdot(d: float, t_s: float) -> float:
    t = t_s / 60
    v = d / t
    cost = -4.60 + 0.182258 * v + 0.000104 * v * v
    frac = 0.8 + 0.1894393 * math.exp(-0.012778 * t) + 0.2989558 * math.exp(-0.1932605 * t)
    return cost / frac


def time_for_vdot(v: float, d: float) -> float:
    lo, hi = 120.0, 36000.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if vdot(d, mid) > v:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def ols(xs: list[float], ys: list[float]) -> dict[str, float] | None:
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True))
    slope = sxy / sxx
    icpt = my - slope * mx
    sse = sum((y - (icpt + slope * x)) ** 2 for x, y in zip(xs, ys, strict=True))
    sst = sum((y - my) ** 2 for y in ys)
    df = n - 2
    s2 = sse / df if df > 0 else float("nan")
    return {"n": n, "slope": slope, "intercept": icpt, "mx": mx, "sxx": sxx, "sse": sse, "s2": s2,
            "r2": 1 - sse / sst if sst > 0 else 1.0, "df": df,
            "se_slope": math.sqrt(s2 / sxx) if df > 0 else float("nan")}


def t_crit(df: int) -> float:
    for k in sorted(T975, reverse=True):
        if df >= k:
            return T975[k]
    return 1.96 if df > 30 else T975[1]


# ---------------------------------------------------------------- efforts
def load_efforts(conn: sqlite3.Connection, since: str, include_indoor: bool, include_trail: bool,
                 use_gap: bool = True) -> list[dict[str, Any]]:
    table = "best_efforts_gap" if use_gap else "best_efforts"
    extra = "be.covered_m AS covered_m" if use_gap else "be.distance_m AS covered_m"
    rows = conn.execute(
        f"SELECT be.activity_id, be.distance_m, be.time_s, be.avg_hr, be.ascent_m, be.gap_s, {extra}, a.start_time, "
        "a.sport, a.name, (ex.activity_id IS NOT NULL) AS excluded, (rm.activity_id IS NOT NULL) AS is_race "
        f"FROM {table} be JOIN activities a ON a.id=be.activity_id "
        "LEFT JOIN effort_exclusions ex ON ex.activity_id=be.activity_id "
        "LEFT JOIN race_marks rm ON rm.activity_id=be.activity_id "
        "WHERE a.start_time >= ? ORDER BY be.distance_m, be.time_s", (since,)).fetchall()
    out = []
    for r in rows:
        kind = run_kind(r["sport"]) or "road"
        flags, reasons = [], []
        if r["excluded"]:
            reasons.append("excluded by you")
        if kind == "indoor" and not include_indoor:
            reasons.append("treadmill/indoor (turned off)")
        if kind == "trail" and not use_gap:
            reasons.append("trail run (needs grade-adjusted pace, which is off)")
        elif kind == "trail" and not include_trail:
            reasons.append("trail run (turned off)")
        if r["distance_m"] / r["time_s"] > MAX_SPEED:
            reasons.append("implausibly fast (likely a GPS glitch)")
        if r["gap_s"] and r["gap_s"] > 0.05 * r["time_s"]:
            flags.append("includes pauses (time is conservative)")
        if kind != "road":
            flags.append(kind)
        adj = ""
        if use_gap and r["covered_m"] and abs(r["covered_m"] - r["distance_m"]) > 0.005 * r["distance_m"]:
            adj = (f"Grade-adjusted: {r['covered_m'] / 1000:.2f} km actually run with {r['ascent_m'] or 0:.0f} m of climbing "
                   f"counts as {r['distance_m'] / 1000:.2f} km of flat running (Minetti cost ratios).")
            flags.append("grade-adjusted")
        out.append({"activity_id": r["activity_id"], "date": r["start_time"], "name": r["name"],
                    "sport": r["sport"], "kind": kind, "distance_m": r["distance_m"], "time_s": r["time_s"],
                    "pace_s_per_km": r["time_s"] / (r["distance_m"] / 1000), "avg_hr": r["avg_hr"],
                    "ascent_m": r["ascent_m"], "flags": flags, "used": not reasons, "not_used_because": reasons,
                    "is_race": bool(r["is_race"]), "covered_m": r["covered_m"], "adjustment": adj})
    return out


def best_per_distance(efforts: list[dict[str, Any]]) -> dict[float, dict[str, Any]]:
    best: dict[float, dict[str, Any]] = {}
    for e in efforts:
        if e["used"] and (e["distance_m"] not in best or e["time_s"] < best[e["distance_m"]]["time_s"]):
            best[e["distance_m"]] = e
    return best


def brief(e: dict[str, Any]) -> dict[str, Any]:
    return {k: e[k] for k in ("activity_id", "date", "name", "distance_m", "time_s")}


# ---------------------------------------------------------------- methods
def method_riegel(target: float, sources: list[dict[str, Any]], k: float, mid: str, name: str,
                  scenario: bool, note: str) -> dict[str, Any]:
    near = min(sources, key=lambda s: abs(math.log(target / s["distance_m"])))
    t = riegel(near["time_s"], near["distance_m"], target, k)
    steps = [
        f"Formula: T2 = T1 x (D2 / D1)^k, with k = {k}.",
        f"Nearest effort to the target: {km(near['distance_m'])} in {fmt_time(near['time_s'])} "
        f"({near['date'][:10]}), so T1 = {near['time_s']:.0f} s, D1 = {near['distance_m']:.1f} m.",
        f"D2 / D1 = {target:.1f} / {near['distance_m']:.1f} = {target / near['distance_m']:.4f}",
        f"({target / near['distance_m']:.4f})^{k} = {(target / near['distance_m']) ** k:.4f}",
        f"T2 = {near['time_s']:.0f} x {(target / near['distance_m']) ** k:.4f} = {t:.0f} s = {fmt_time(t)}",
    ]
    by_source = [{"from": brief(s), "time_s": riegel(s["time_s"], s["distance_m"], target, k)} for s in sources]
    return {"id": mid, "name": name, "time_s": t, "scenario": scenario, "citation": "fetch_everyone" if scenario else "riegel1981",
            "source_effort": brief(near), "steps": steps, "by_source": by_source, "note": note,
            "status": "ok", "warnings": []}


def method_fit(target: float, sources: list[dict[str, Any]]) -> dict[str, Any]:
    pts = [(math.log(s["distance_m"]), math.log(s["time_s"])) for s in sources]
    base = {"id": "riegel_fit", "name": "Your own power law (fitted exponent)", "citation": "riegel1981",
            "scenario": False, "warnings": []}
    if len(sources) < 3:
        return base | {"time_s": None, "status": "not_enough_data", "steps": [
            f"Needs at least 3 different race distances in your efforts (excluding the {km(target)} you are "
            f"predicting); you have {len(sources)}."]}
    fit = ols([p[0] for p in pts], [p[1] for p in pts])
    if fit is None or fit["df"] < 1:
        return base | {"time_s": None, "status": "not_enough_data", "steps": ["The fit could not be computed."]}
    k, a = fit["slope"], fit["intercept"]
    x0 = math.log(target)
    yhat = a + k * x0
    t = math.exp(yhat)
    se_pred = math.sqrt(fit["s2"] * (1 + 1 / fit["n"] + (x0 - fit["mx"]) ** 2 / fit["sxx"]))
    tc = t_crit(fit["df"])
    lo, hi = math.exp(yhat - tc * se_pred), math.exp(yhat + tc * se_pred)
    steps = [
        "Fit a straight line through ln(time) versus ln(distance) for your best efforts "
        "(ordinary least squares). The slope is your personal exponent k, so T = e^a x D^k.",
        *[f"  {km(s['distance_m'])}: {fmt_time(s['time_s'])} ({s['date'][:10]}) -> ln D = "
          f"{math.log(s['distance_m']):.4f}, ln T = {math.log(s['time_s']):.4f}" for s in sources],
        f"Fitted k = {k:.3f} (standard error {fit['se_slope']:.3f}), a = {a:.4f}, R2 = {fit['r2']:.4f}, "
        f"{fit['n']} efforts, {fit['df']} degrees of freedom. The textbook value is 1.06.",
        f"Predict: ln T = {a:.4f} + {k:.3f} x ln({target:.1f}) = {yhat:.4f} -> T = {t:.0f} s = {fmt_time(t)}",
        f"95% prediction interval {fmt_time(lo)} to {fmt_time(hi)} (t = {tc} for {fit['df']} degrees of freedom; "
        f"wide intervals mean little data).",
    ]
    warnings = []
    status = "ok"
    if not 1.0 <= k <= 1.3:
        status = "reference_only"
        warnings.append(f"Fitted k = {k:.2f} is outside the plausible 1.00 to 1.30 range, so this is shown for "
                        "information but left out of the headline.")
    return base | {"time_s": t, "status": status, "steps": steps, "warnings": warnings, "k": k, "se_k": fit["se_slope"],
                   "r2": fit["r2"], "n": fit["n"], "interval_s": [lo, hi], "points": [brief(s) for s in sources]}


def method_cs(target: float, pool: list[dict[str, Any]]) -> dict[str, Any]:
    pts = [s for s in pool if CS_MIN_S <= s["time_s"] <= CS_MAX_S]
    base = {"id": "critical_speed", "name": "Critical speed (two-parameter model)", "citation": "poole2016",
            "scenario": False, "warnings": []}
    if len(pts) < 3:
        return base | {"time_s": None, "status": "not_enough_data", "steps": [
            f"Needs at least 3 efforts lasting between {CS_MIN_S // 60} and {CS_MAX_S // 60} minutes at different "
            f"distances; you have {len(pts)}."]}
    fit = ols([s["time_s"] for s in pts], [s["distance_m"] for s in pts])
    if fit is None or fit["df"] < 1 or fit["slope"] <= 0:
        return base | {"time_s": None, "status": "not_enough_data", "steps": ["The fit could not be computed."]}
    cs, dprime = fit["slope"], fit["intercept"]
    t = (target - dprime) / cs
    steps = [
        "Model: distance = CS x time + D'. CS is the speed you could hold 'indefinitely' in theory; D' is a "
        "fixed reserve of distance you can cover above it. Fit by least squares over efforts of "
        f"{CS_MIN_S // 60} to {CS_MAX_S // 60} minutes:",
        *[f"  {km(s['distance_m'])} in {fmt_time(s['time_s'])} ({s['date'][:10]})" for s in pts],
        f"CS = {cs:.3f} m/s ({fmt_pace(1000 / cs)}), D' = {dprime:.0f} m, R2 = {fit['r2']:.4f}, {fit['n']} efforts.",
        f"Solve for time: t = (D - D') / CS = ({target:.1f} - {dprime:.0f}) / {cs:.3f} = {t:.0f} s = {fmt_time(t)}",
    ]
    warnings, status = [], "ok"
    if not CS_MIN_S <= t <= CS_MAX_S:
        status = "reference_only"
        warnings.append(f"The predicted time ({fmt_time(t)}) is outside the {CS_MIN_S // 60} to {CS_MAX_S // 60} "
                        "minute range this model is used for here, where it tends to overestimate what you can hold. "
                        "Shown for reference, left out of the headline.")
    return base | {"time_s": t, "status": status, "steps": steps, "warnings": warnings, "cs": cs, "dprime": dprime,
                   "r2": fit["r2"], "n": fit["n"], "points": [brief(s) for s in pts]}


def method_vdot(target: float, sources: list[dict[str, Any]]) -> dict[str, Any]:
    near = min(sources, key=lambda s: abs(math.log(target / s["distance_m"])))
    v = vdot(near["distance_m"], near["time_s"])
    t = time_for_vdot(v, target)
    mins = near["time_s"] / 60
    speed = near["distance_m"] / mins
    cost = -4.60 + 0.182258 * speed + 0.000104 * speed ** 2
    frac = 0.8 + 0.1894393 * math.exp(-0.012778 * mins) + 0.2989558 * math.exp(-0.1932605 * mins)
    steps = [
        "Daniels/Gilbert equations (t in minutes, v in metres per minute):",
        "  oxygen cost = -4.60 + 0.182258 v + 0.000104 v^2",
        "  fraction of VO2max held = 0.8 + 0.1894393 e^(-0.012778 t) + 0.2989558 e^(-0.1932605 t)",
        "  VDOT = oxygen cost / fraction",
        f"Nearest effort: {km(near['distance_m'])} in {fmt_time(near['time_s'])} ({near['date'][:10]}): "
        f"t = {mins:.2f} min, v = {speed:.1f} m/min",
        f"  oxygen cost = {cost:.2f}, fraction = {frac:.4f} -> VDOT = {v:.1f}",
        f"Find the time at which a VDOT of {v:.1f} gives exactly that on {target:.1f} m (solved numerically): "
        f"{t:.0f} s = {fmt_time(t)}",
    ]
    return {"id": "vdot", "name": "VDOT (Daniels/Gilbert)", "time_s": t, "citation": "daniels1979", "scenario": False,
            "source_effort": brief(near), "steps": steps, "status": "ok", "warnings": [], "vdot": v,
            "note": "VDOT is a fitness score from race performance, not a measured VO2max."}


def annotate_range(m: dict[str, Any]) -> None:
    t = m.get("time_s")
    if t is not None and m["status"] == "ok" and not RIEGEL_MIN_S <= t <= RIEGEL_MAX_S and m["id"] != "critical_speed":
        m["status"] = "extrapolated"
        m["warnings"].append(f"The predicted time ({fmt_time(t)}) is outside the 3.5 to 230 minute window the app "
                             "allows (Riegel's own running data covered 3.5 to 147 minutes); treat it as an extrapolation.")


def predict_target(key: str, label: str, target: float, efforts: list[dict[str, Any]]) -> dict[str, Any]:
    best = best_per_distance(efforts)
    actual = best.get(target)
    others = [e for d, e in best.items() if d != target]
    sources = [e for e in others if RIEGEL_MIN_S <= e["time_s"] <= RIEGEL_MAX_S]
    out: dict[str, Any] = {"key": key, "label": label, "distance_m": target,
                           "actual_best": brief(actual) if actual else None, "methods": [], "headline": None,
                           "support": None, "notes": []}
    if not sources:
        out["notes"].append("No usable efforts yet. A usable effort is the fastest time over 3, 5, 10, 15 km, a "
                            "half marathon or more inside one of your runs (3.5 to 230 minutes long), after the "
                            "filters you have set.")
        return out
    longest = max(s["distance_m"] for s in sources)
    ratio = target / longest
    level, text = (("good", f"The target is {ratio:.1f}x the longest effort used ({km(longest)}): well supported.")
                   if ratio <= 1.5 else
                   ("extrapolated", f"The target is {ratio:.1f}x the longest effort used ({km(longest)}): extrapolated.")
                   if ratio <= 3 else
                   ("weak", f"The target is {ratio:.1f}x the longest effort used ({km(longest)}): a weak extrapolation."))
    out["support"] = {"level": level, "ratio": ratio, "longest_source_m": longest, "text": text,
                      "rule": "App rule of thumb (not from the literature): up to 1.5x the longest effort is well "
                              "supported, up to 3x is extrapolated, beyond that is weak."}
    methods = [
        method_riegel(target, sources, 1.06, "riegel_106", "Riegel power law (k = 1.06)", False,
                      "The standard textbook version."),
        method_fit(target, sources),
        method_cs(target, [e for e in others if e["distance_m"] <= HALF]),
        method_vdot(target, sources),
        method_riegel(target, sources, 1.15, "riegel_115", "Conservative scenario (k = 1.15)", True,
                      "A scenario, not a fit: many experienced marathoners' times imply an exponent nearer 1.15."),
    ]
    for m in methods:
        annotate_range(m)
    out["methods"] = methods
    used = [m["time_s"] for m in methods if m.get("time_s") and m["status"] in ("ok", "extrapolated")]
    if used:
        out["headline"] = {"middle_s": median(used), "low_s": min(used), "high_s": max(used), "n_methods": len(used),
                           "pace_s_per_km": median(used) / (target / 1000),
                           "how": f"Methods counted: {', '.join(m['name'] for m in methods if m.get('time_s') and m['status'] in ('ok', 'extrapolated'))}. "
                                  f"Range = fastest to slowest of their predictions ({fmt_time(min(used))} to "
                                  f"{fmt_time(max(used))}); middle = their median ({fmt_time(median(used))}). "
                                  "Methods marked 'reference only' or 'not enough data' are shown but not counted."}
    return out


# ---------------------------------------------------------------- back-test
def local_best(e: dict[str, Any], efforts: list[dict[str, Any]], days: int = 60) -> bool:
    d = datetime.fromisoformat(e["date"])
    for o in efforts:
        if o is e or o["distance_m"] != e["distance_m"] or not o["used"]:
            continue
        if abs((datetime.fromisoformat(o["date"]) - d).days) <= days and o["time_s"] < e["time_s"]:
            return False
    return True


def anchor_row(target: float, a: dict[str, Any], efforts: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Predict one past effort using only efforts from the 1 to 90 days before it."""
    d = datetime.fromisoformat(a["date"])
    prior = [e for e in efforts if e["used"] and e["distance_m"] != target and e["activity_id"] != a["activity_id"]
             and RIEGEL_MIN_S <= e["time_s"] <= RIEGEL_MAX_S
             and timedelta(days=1) <= d - datetime.fromisoformat(e["date"]) <= timedelta(days=90)]
    src = list(best_per_distance(prior).values())
    if not src:
        return None
    row: dict[str, Any] = {"on": a["date"][:10], "activity_id": a["activity_id"], "name": a["name"],
                           "actual_s": a["time_s"], "is_race": a.get("is_race", False), "predictions": {},
                           "sources": [brief(s_) for s_ in src]}
    for mid, fn in (("riegel_106", lambda: method_riegel(target, src, 1.06, "x", "x", False, "")),
                    ("riegel_fit", lambda: method_fit(target, src)), ("vdot", lambda: method_vdot(target, src))):
        m = fn()
        if m.get("time_s"):
            row["predictions"][mid] = {"time_s": m["time_s"], "error_pct": (m["time_s"] - a["time_s"]) / a["time_s"] * 100}
    return row if row["predictions"] else None


def backtest(target: float, efforts: list[dict[str, Any]]) -> dict[str, Any]:
    at_target = [e for e in efforts if e["used"] and e["distance_m"] == target]
    races = [e for e in at_target if e.get("is_race")]
    use_races = len(races) >= 3
    anchors = races if use_races else [e for e in at_target if local_best(e, efforts)]
    errs: dict[str, list[float]] = {"riegel_106": [], "riegel_fit": [], "vdot": []}
    rows = []
    for a in anchors:
        row = anchor_row(target, a, efforts)
        if row:
            rows.append(row)
            for mid, p_ in row["predictions"].items():
                errs[mid].append(p_["error_pct"])
    summary = {}
    for mid, e in errs.items():
        if e:
            s_ = sorted(e)
            summary[mid] = {"n": len(e), "median_error_pct": median(e),
                            "p25": s_[int(0.25 * (len(s_) - 1))], "p75": s_[int(0.75 * (len(s_) - 1))],
                            "within_3pct": sum(abs(x) <= 3 for x in e) / len(e),
                            "within_5pct": sum(abs(x) <= 5 for x in e) / len(e)}
    race_rows = [r for r in (anchor_row(target, a, efforts) for a in races) if r]
    basis = ("Each check takes one of YOUR MARKED RACES at this distance" if use_races else
             "Each check takes one of your own efforts at this distance that was your fastest within 60 days either "
             "side (a stand-in for 'raced it'; mark real races on their activity page and these will use them once "
             "you have 3)")
    return {"summary": summary, "checks": rows[-12:], "races": race_rows, "n_anchors": len(anchors),
            "basis": "races" if use_races else "local_bests",
            "how": basis + ", predicts it using only efforts from the 90 days before, and reports "
                   "(predicted - actual) / actual. Negative = predicted faster than you ran. "
                   + ("" if use_races else "Your best efforts include training runs that were not all-out, so expect an "
                      "optimistic (negative) bias.")}


def gap_model() -> dict[str, Any]:
    pts = [-0.20, -0.10, -0.05, 0.0, 0.05, 0.10, 0.20]
    return {
        "name": "Grade-adjusted pace (Minetti et al. 2002 energy cost of running)",
        "steps": [
            "A metre of running costs different energy on different slopes. Minetti et al. measured this on a "
            "treadmill and fitted a polynomial: cost(i) = 155.4 i^5 - 30.4 i^4 - 43.3 i^3 + 46.3 i^2 + 19.5 i + 3.6 "
            "(joules per kg per metre, i = slope as a fraction, so 0.10 = 10% uphill).",
            "Cost ratio = cost(i) / cost(0) = cost(i) / 3.6. Uphill ratios are above 1, gentle downhills below 1.",
            "For every step of a run the app multiplies the real distance by the ratio for that step's grade. The total "
            "is 'flat-equivalent distance': the flat running that would cost the same energy.",
            "Best efforts are then found on that axis, so a 5 km effort means 5 km of flat-equivalent running, and its "
            "time is your grade-adjusted time.",
            f"Grade is measured from altitude over +/- 25 m of running and capped at +/-{int(0.30 * 100)}%, because "
            "steeper readings are almost always altitude noise. Treadmill runs have no altitude, so they are unchanged.",
        ],
        "table": [{"grade_pct": g * 100, "cost_j_per_kg_m": minetti_cost(g), "ratio": cost_ratio(g)} for g in pts],
        "citation": "minetti2002", "citations": references.get(["minetti2002"]),
        "limits": "The polynomial is exactly the one in the paper (checked against the full text). It was fitted to 10 "
                  "elite mountain-endurance men running on a smooth treadmill. The measured level cost was 3.40 +/- 0.24 "
                  "J/kg/m while the polynomial's constant is 3.6; the authors found downhill running about 40% cheaper "
                  "than earlier data from sedentary people and caution that rougher ground than a treadmill raises the "
                  "cost. So adjusted times are approximate: downhill credit may be generous for runners not trained on "
                  "descents, and soft, rocky or technical trail costs more than the model says.",
    }


def training_context(conn: sqlite3.Connection, today: datetime) -> dict[str, Any]:
    since = (today - timedelta(days=56)).isoformat()
    rows = [r for r in conn.execute("SELECT sport, distance_m FROM activities WHERE start_time >= ? AND distance_m > 0",
                                    (since,)) if run_kind(r["sport"])]
    total = sum(r["distance_m"] for r in rows)
    return {"weeks": 8, "runs": len(rows), "weekly_km": total / 8000, "longest_run_km": max((r["distance_m"] for r in rows), default=0) / 1000,
            "text": "Average weekly running distance and the longest single run over the last 8 weeks. No adjustment "
                    "is made for these; they are here so you can judge how much endurance sits behind a half "
                    "marathon or marathon prediction."}


def build(conn: sqlite3.Connection, window_days: int = 365, include_indoor: bool = True,
          include_trail: bool = True, use_gap: bool = True, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    since = (now - timedelta(days=window_days)).isoformat()
    # the back-test looks further back than the prediction window
    all_efforts = load_efforts(conn, (now - timedelta(days=max(window_days, 1095))).isoformat(), include_indoor, include_trail, use_gap)
    efforts = [e for e in all_efforts if e["date"] >= since]
    targets = []
    for key, label, d in TARGETS:
        t = predict_target(key, label, d, efforts)
        t["backtest"] = backtest(d, all_efforts)
        targets.append(t)
    best = best_per_distance(efforts)
    return {"generated_at": now.isoformat(timespec="seconds"),
            "mission": "Use your data to train smarter, and always show the math.",
            "settings": {"window_days": window_days, "include_indoor": include_indoor, "include_trail": include_trail,
                         "use_gap": use_gap},
            "gap_model": gap_model(),
            "efforts": [e for e in efforts if e["distance_m"] in DISTANCES],
            "sources": [brief(e) | {"pace_s_per_km": e["pace_s_per_km"]} for _, e in sorted(best.items())],
            "targets": targets, "context": training_context(conn, now), "citations": references.get(CITATION_IDS),
            "caveats": CAVEATS}
