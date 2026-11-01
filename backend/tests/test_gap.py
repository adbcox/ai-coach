import pytest

from app import db, efforts
from app.efforts import best_efforts, cost_ratio, equivalent_distance, grades, minetti_cost
from tests.test_predictions import insert_run, run_samples


def test_minetti_model_matches_its_known_shape():
    assert minetti_cost(0.0) == pytest.approx(3.6)
    assert minetti_cost(-0.20) == pytest.approx(1.80, abs=0.05)   # the cheapest slope is about -20%
    assert minetti_cost(0.45) == pytest.approx(19.4, abs=0.2)      # very steep uphill costs ~5x the flat
    assert 3.4 < minetti_cost(-0.45) < 4.2                         # sources report 3.5 to 3.9 at -45%
    assert cost_ratio(0.0) == pytest.approx(1.0)
    assert cost_ratio(0.05) > 1.2 and cost_ratio(-0.10) < 1.0
    assert minetti_cost(0.9) == minetti_cost(0.45)                 # the model is only defined to +/-45%


def test_grades_from_a_constant_slope():
    d = [float(x) for x in range(0, 1000, 5)]
    alt = [x * 0.05 for x in d]  # 5% uphill
    g = grades(d, alt)
    assert g[100] == pytest.approx(0.05, abs=1e-6) and g[0] == pytest.approx(0.05, abs=1e-6)
    assert grades(d, [None] * len(d)) == [0.0] * len(d)           # no altitude = no adjustment
    steep = grades(d, [x * 2.0 for x in d])
    assert max(steep) == pytest.approx(efforts.GRADE_LIMIT)       # absurd slopes are capped as noise


def test_equivalent_distance_on_a_hill():
    d = [float(x) for x in range(0, 5001, 5)]
    flat = equivalent_distance(d, [0.0] * len(d))
    assert flat[-1] == pytest.approx(5000.0)
    up = equivalent_distance(d, [x * 0.05 for x in d])
    assert up[-1] == pytest.approx(5000 * cost_ratio(0.05), rel=1e-3)  # about 6.5 km of flat effort


def test_best_effort_on_the_grade_adjusted_axis():
    t, d = run_samples([(6000, 3.0)])           # 6 km at 3 m/s ...
    alt = [x * 0.05 for x in d]                 # ... all on a 5% hill
    eq = equivalent_distance(d, alt)
    five_gap = next(e for e in best_efforts(t, eq, None, alt, raw_d=d) if e["distance_m"] == 5000.0)
    # flat speed equivalent = 3.0 x ratio(0.05) = 3.9 m/s, so 5 km flat-equivalent takes about 1281 s
    assert five_gap["time_s"] == pytest.approx(5000 / (3.0 * cost_ratio(0.05)), abs=2)
    assert five_gap["covered_m"] == pytest.approx(5000 / cost_ratio(0.05), rel=0.01)  # real metres run
    raw = next(e for e in best_efforts(t, d, None, alt) if e["distance_m"] == 5000.0)
    assert five_gap["time_s"] < raw["time_s"]    # a hill makes the adjusted time faster than the raw time


def test_scanner_stores_both_raw_and_adjusted_efforts(authed, settings):
    from datetime import UTC, datetime

    conn = db.connect(settings.db_path)
    conn.execute("INSERT INTO activities (id, source, source_id, start_time, sport, name, distance_m, duration_s, "
                 "has_samples, created_at) VALUES (400, 'garmin', '400', ?, 'trail_running', 'Hills', 6000, 2000, 1, 'x')",
                 (datetime.now(UTC).isoformat(),))
    t, d = run_samples([(6000, 3.0)])
    conn.executemany("INSERT INTO samples (activity_id, t, dist, alt, hr) VALUES (400, ?, ?, ?, 150)",
                     [(1_700_000_000 + int(x), y, y * 0.05) for x, y in zip(t, d, strict=True)])
    conn.commit()
    efforts.EffortScanner(settings).run_blocking()
    raw = conn.execute("SELECT time_s FROM best_efforts WHERE activity_id=400 AND distance_m=5000").fetchone()
    gap = conn.execute("SELECT time_s, covered_m FROM best_efforts_gap WHERE activity_id=400 AND distance_m=5000").fetchone()
    assert gap["time_s"] < raw["time_s"] and gap["covered_m"] < 5000
    conn.close()


def test_trail_runs_are_included_only_when_grade_adjustment_is_on(authed, settings):
    from datetime import UTC, datetime, timedelta

    conn = db.connect(settings.db_path)
    day = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    insert_run(conn, 500, "trail_running", day, [(5000, 1500), (10000, 3200)])
    insert_run(conn, 501, "treadmill_running", day, [(5000, 1600)])
    conn.commit()
    conn.close()
    on = authed.get("/api/predictions").json()
    trail = next(e for e in on["efforts"] if e["activity_id"] == 500 and e["distance_m"] == 5000)
    assert trail["used"] is True
    off = authed.get("/api/predictions?use_gap=false").json()
    trail = next(e for e in off["efforts"] if e["activity_id"] == 500 and e["distance_m"] == 5000)
    treadmill = next(e for e in off["efforts"] if e["activity_id"] == 501)
    assert trail["used"] is False and "needs grade-adjusted pace" in trail["not_used_because"][0]
    assert treadmill["used"] is True          # treadmill runs do not depend on the grade adjustment
    only_off = authed.get("/api/predictions?include_trail=false").json()
    assert "turned off" in next(e for e in only_off["efforts"] if e["activity_id"] == 500)["not_used_because"][0]
