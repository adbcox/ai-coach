"""Code-computed correlations between training outcomes (y) and life/load
factors (x). The LLM reads results, never the raw numbers.

Methods:
  - Spearman rho for continuous y and x. Fisher z-transform → 95 % CI.
  - Mann-Whitney U for a continuous y with a boolean/0-1 x (travel, busy,
    sick). Effect size `r = Z / sqrt(n)` stored in `rho` for consistency;
    CI computed via the same Fisher transform of `r`.

Guard rails:
  - n < 30 → the pair is skipped (row deleted).
  - All results are labelled "association, not cause" by the query helper
    at the API boundary.

Lags: ℓ ∈ {0, 1, 2, 3, 7} days. x values at day `d` are paired against y
values at day `d + ℓ`.
"""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

LAGS = (0, 1, 2, 3, 7)
MIN_N = 30

# (y_key, SQL fragment that picks a numeric value per day)
_Y_SELECTORS: dict[str, str] = {
    "readiness.score":  "SELECT day AS day, score AS v FROM readiness_day",
    "readiness.hrv":    "SELECT day AS day, hrv_part AS v FROM readiness_day",
    "readiness.rhr":    "SELECT day AS day, rhr_part AS v FROM readiness_day",
    "readiness.sleep":  "SELECT day AS day, sleep_part AS v FROM readiness_day",
    "load.ctl":         "SELECT day AS day, ctl AS v FROM training_load_day",
    "load.atl":         "SELECT day AS day, atl AS v FROM training_load_day",
    "load.tsb":         "SELECT day AS day, tsb AS v FROM training_load_day",
    "load.acwr":        "SELECT day AS day, acwr AS v FROM training_load_day",
}

# (x_key, SQL fragment, is_boolean)
_X_SELECTORS: dict[str, tuple[str, bool]] = {
    "weather.temp_c":        ("SELECT day AS day, apparent_mean_c AS v FROM weather_day", False),
    "weather.dew_point_c":   ("SELECT day AS day, dew_point_mean_c AS v FROM weather_day", False),
    "weather.humidity_pct":  ("SELECT day AS day, humidity_mean_pct AS v FROM weather_day", False),
    "weather.precip_mm":     ("SELECT day AS day, precip_mm AS v FROM weather_day", False),
    "life.travel":           ("SELECT day AS day, travel AS v FROM life_signal_day", True),
    "life.busy":             ("SELECT day AS day, busy AS v FROM life_signal_day", True),
    "life.sick":             ("SELECT day AS day, sick AS v FROM life_signal_day", True),
    "life.alcohol_units":    ("SELECT day AS day, alcohol_units AS v FROM life_signal_day", False),
    "checkin.sleep_feel":    ("SELECT day AS day, sleep_feel AS v FROM checkins", False),
    "checkin.stress":        ("SELECT day AS day, stress AS v FROM checkins", False),
    "hass.bedroom_temp":     ("SELECT day AS day, bedroom_temp_c_night AS v FROM ha_daily", False),
}


@dataclass
class CorrResult:
    y: str
    x: str
    lag_days: int
    n: int
    rho: float
    ci_low: float
    ci_high: float
    method: str          # "spearman" or "mwu"
    p_approx: float


def _day_map(conn: sqlite3.Connection, sql: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in conn.execute(sql).fetchall():
        v = row["v"]
        if v is None:
            continue
        try:
            out[row["day"]] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def _rankdata(values: list[float]) -> list[float]:
    """Average-rank implementation (ties → mean rank). O(n log n)."""
    if not values:
        return []
    sorted_idx = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(sorted_idx):
        j = i
        while j + 1 < len(sorted_idx) and values[sorted_idx[j + 1]] == values[sorted_idx[i]]:
            j += 1
        avg = (i + j) / 2 + 1  # +1 because ranks are 1-based
        for k in range(i, j + 1):
            ranks[sorted_idx[k]] = avg
        i = j + 1
    return ranks


def _spearman(xs: list[float], ys: list[float]) -> tuple[float, float, float, float]:
    """Return (rho, ci_low, ci_high, p_approx)."""
    n = len(xs)
    if n < 3:
        return float("nan"), float("nan"), float("nan"), float("nan")
    rx = _rankdata(xs)
    ry = _rankdata(ys)
    mean_rx = sum(rx) / n
    mean_ry = sum(ry) / n
    num = sum((rx[i] - mean_rx) * (ry[i] - mean_ry) for i in range(n))
    den_x = math.sqrt(sum((v - mean_rx) ** 2 for v in rx))
    den_y = math.sqrt(sum((v - mean_ry) ** 2 for v in ry))
    if den_x == 0 or den_y == 0:
        return float("nan"), float("nan"), float("nan"), float("nan")
    rho = num / (den_x * den_y)
    rho_c = max(-0.9999, min(0.9999, rho))
    z = 0.5 * math.log((1 + rho_c) / (1 - rho_c))
    se = 1.0 / math.sqrt(n - 3) if n > 3 else float("inf")
    z_lo, z_hi = z - 1.96 * se, z + 1.96 * se
    ci_lo = (math.exp(2 * z_lo) - 1) / (math.exp(2 * z_lo) + 1)
    ci_hi = (math.exp(2 * z_hi) - 1) / (math.exp(2 * z_hi) + 1)
    # Approximate two-sided p-value via normal approximation of the t-statistic.
    if 1 - rho * rho <= 0:
        p = 0.0
    else:
        t = rho * math.sqrt((n - 2) / (1 - rho * rho))
        p = 2 * (1 - _std_normal_cdf(abs(t) / math.sqrt(n - 2 + t * t)))
    return rho, ci_lo, ci_hi, p


def _std_normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _mwu(continuous: list[float], boolean: list[int]) -> tuple[float, float, float, float]:
    """Mann-Whitney U with effect size r = Z/sqrt(n). Return
    (r, ci_low, ci_high, p_approx)."""
    pos = [v for v, b in zip(continuous, boolean, strict=False) if b == 1]
    neg = [v for v, b in zip(continuous, boolean, strict=False) if b == 0]
    n1, n2 = len(pos), len(neg)
    if n1 < 3 or n2 < 3:
        return float("nan"), float("nan"), float("nan"), float("nan")
    combined = pos + neg
    ranks = _rankdata(combined)
    r1 = sum(ranks[:n1])
    U1 = r1 - n1 * (n1 + 1) / 2
    U = min(U1, n1 * n2 - U1)
    mu = n1 * n2 / 2
    sigma = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)
    if sigma == 0:
        return float("nan"), float("nan"), float("nan"), float("nan")
    z = (U - mu) / sigma
    n = n1 + n2
    r = z / math.sqrt(n)
    r_c = max(-0.9999, min(0.9999, r))
    fz = 0.5 * math.log((1 + r_c) / (1 - r_c))
    se = 1.0 / math.sqrt(n - 3) if n > 3 else float("inf")
    z_lo, z_hi = fz - 1.96 * se, fz + 1.96 * se
    ci_lo = (math.exp(2 * z_lo) - 1) / (math.exp(2 * z_lo) + 1)
    ci_hi = (math.exp(2 * z_hi) - 1) / (math.exp(2 * z_hi) + 1)
    p = 2 * (1 - _std_normal_cdf(abs(z)))
    return r, ci_lo, ci_hi, p


def _shift_day(day: str, lag: int) -> str:
    try:
        d = date.fromisoformat(day)
    except ValueError:
        return day
    return (d + timedelta(days=lag)).isoformat()


def recompute_all(conn: sqlite3.Connection) -> int:
    """Rebuild the entire `correlations` table. Returns row count."""
    ys = {k: _day_map(conn, sql) for k, sql in _Y_SELECTORS.items()}
    xs = {k: (_day_map(conn, sql), is_bool) for k, (sql, is_bool) in _X_SELECTORS.items()}
    conn.execute("DELETE FROM correlations")
    now = datetime.now(UTC).isoformat(timespec="seconds")
    written = 0
    for y_key, y_map in ys.items():
        for x_key, (x_map, is_bool) in xs.items():
            for lag in LAGS:
                pairs: list[tuple[float, float]] = []
                for x_day, x_val in x_map.items():
                    y_day = _shift_day(x_day, lag)
                    y_val = y_map.get(y_day)
                    if y_val is None:
                        continue
                    pairs.append((x_val, y_val))
                if len(pairs) < MIN_N:
                    continue
                xs_vals = [p[0] for p in pairs]
                ys_vals = [p[1] for p in pairs]
                if is_bool:
                    rho, lo, hi, p = _mwu(ys_vals, [int(v) for v in xs_vals])
                    method = "mwu"
                else:
                    rho, lo, hi, p = _spearman(xs_vals, ys_vals)
                    method = "spearman"
                if math.isnan(rho):
                    continue
                conn.execute(
                    "INSERT INTO correlations (y, x, lag_days, n, rho, ci_low, "
                    "ci_high, method, p_approx, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (y_key, x_key, lag, len(pairs), rho, lo, hi, method, p, now),
                )
                written += 1
    conn.commit()
    return written


def top_for(
    conn: sqlite3.Connection,
    *,
    y: str | None = None,
    min_abs_rho: float = 0.25,
    min_n: int = 30,
    limit: int = 20,
) -> list[dict]:
    where = ["ABS(rho) >= ?", "n >= ?"]
    params: list = [min_abs_rho, min_n]
    if y is not None:
        where.append("y = ?")
        params.append(y)
    rows = conn.execute(
        "SELECT y, x, lag_days, n, rho, ci_low, ci_high, method, p_approx, "
        "       computed_at FROM correlations "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY ABS(rho) DESC LIMIT ?",
        (*params, limit),
    ).fetchall()
    return [dict(row) for row in rows]
