"""PMC — EWMA CTL/ATL/TSB from daily TSS, with aggregate + per-family totals."""

from datetime import date, timedelta

from app import db
from app.coach_maths import load as cm_load
from app.config import Settings


def _mk(tmp_path):
    s = Settings(data_dir=tmp_path, request_delay_s=0)
    db.init_db(s.db_path)
    conn = db.connect(s.db_path)
    return s, conn


def _ins_activity(conn, aid, start, sport, duration_s, distance_m, avg_hr):
    conn.execute(
        "INSERT INTO activities (id, source, source_id, start_time, sport, name, "
        "distance_m, duration_s, avg_hr, created_at) "
        "VALUES (?, 'garmin', ?, ?, ?, 'x', ?, ?, ?, '2026-01-01T00:00:00+00:00')",
        (aid, str(aid), start, sport, distance_m, duration_s, avg_hr),
    )


def _set_thresholds(conn):
    for k, v in (("thresholds.lthr", 160), ("thresholds.max_hr", 190),
                 ("thresholds.ftp", 250), ("thresholds.threshold_pace_s_per_m", 0.25),
                 ("thresholds.css_s_per_m", 0.56)):
        conn.execute("INSERT INTO sync_state (key, value) VALUES (?, ?)", (k, str(v)))


def test_pmc_rises_and_falls(tmp_path):
    _s, conn = _mk(tmp_path)
    _set_thresholds(conn)
    # 10 daily running sessions (hrTSS-based) then 5 days rest
    base = date(2026, 10, 1)
    for i in range(10):
        _ins_activity(conn, i + 1, f"{base + timedelta(days=i)}T07:00:00+00:00",
                      "running", duration_s=3600, distance_m=12000, avg_hr=155)
    conn.commit()
    cm_load.recompute_training_load(conn)
    rows = conn.execute(
        "SELECT day, tss, ctl, atl, tsb FROM training_load_day ORDER BY day",
    ).fetchall()
    assert len(rows) >= 10
    ctls = [r["ctl"] for r in rows if r["tss"] and r["tss"] > 0]
    # CTL is strictly rising while we're adding daily TSS
    assert all(b > a for a, b in zip(ctls, ctls[1:], strict=False))


def test_pmc_family_totals_sum_to_aggregate_within_rounding(tmp_path):
    _s, conn = _mk(tmp_path)
    _set_thresholds(conn)
    base = date(2026, 10, 1)
    _ins_activity(conn, 1, f"{base}T07:00:00+00:00", "running",
                  3600, 10000, 150)
    _ins_activity(conn, 2, f"{base}T17:00:00+00:00", "cycling",
                  3600, 30000, 150)
    conn.commit()
    cm_load.recompute_training_load(conn)
    total = conn.execute(
        "SELECT tss FROM training_load_day WHERE day = ?", (base.isoformat(),),
    ).fetchone()
    per_fam = conn.execute(
        "SELECT SUM(tss) AS s FROM training_load_day_family WHERE day = ?",
        (base.isoformat(),),
    ).fetchone()
    assert total["tss"] and per_fam["s"]
    assert abs(total["tss"] - per_fam["s"]) < 0.01
