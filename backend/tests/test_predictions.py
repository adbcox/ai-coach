import math
from datetime import UTC, datetime, timedelta

import pytest

from app import db, efforts, predict
from app.config import Settings
from app.predict import fmt_time, ols, riegel, time_for_vdot, vdot


# ------------------------------------------------------------------ best efforts
def run_samples(speeds, hz=1.0):
    """speeds: list of (metres, m/s) segments -> (t, dist) arrays at 1 Hz."""
    t, d, now_t, now_d = [0.0], [0.0], 0.0, 0.0
    for metres, v in speeds:
        end = now_d + metres
        while now_d < end:
            now_t += 1 / hz
            now_d = min(end, now_d + v / hz)
            t.append(now_t)
            d.append(now_d)
    return t, d


def test_best_effort_constant_pace_and_interpolation():
    t, d = run_samples([(12000, 3.7)])
    got = {e["distance_m"]: e["time_s"] for e in efforts.best_efforts(t, d)}
    assert got[5000.0] == pytest.approx(5000 / 3.7, abs=0.6)
    assert got[10000.0] == pytest.approx(10000 / 3.7, abs=0.6)
    assert 21097.5 not in got and 42195.0 not in got  # run is too short for those


def test_best_effort_finds_the_fast_part_of_a_run():
    # 6 km easy at 3.0 m/s then 5 km hard at 4.0 m/s
    t, d = run_samples([(6000, 3.0), (5000, 4.0)])
    five = next(e for e in efforts.best_efforts(t, d) if e["distance_m"] == 5000.0)
    assert five["time_s"] == pytest.approx(1250, abs=1.5)
    assert five["start_offset_s"] == pytest.approx(2000, abs=2)  # starts where the hard part starts


def test_best_effort_survives_gps_jitter_and_reports_pauses():
    t, d = run_samples([(6000, 3.0)])
    d[100] = d[100] - 15  # a backwards glitch in cumulative distance
    t2 = [x if i < 1000 else x + 40 for i, x in enumerate(t)]  # a 40 s pause 3 km in, inside every 5 km window
    five = next(e for e in efforts.best_efforts(t2, d) if e["distance_m"] == 5000.0)
    assert five["gap_s"] == pytest.approx(39, abs=1)
    assert five["time_s"] > 5000 / 3.0


def test_run_kind():
    assert efforts.run_kind("running") == "road" and efforts.run_kind("track_running") == "road"
    assert efforts.run_kind("trail_running") == "trail"
    assert efforts.run_kind("treadmill_running") == "indoor" and efforts.run_kind("virtual_run") == "indoor"
    assert efforts.run_kind("cycling") is None and efforts.run_kind(None) is None


# ------------------------------------------------------------------ models
def test_vdot_matches_commonly_quoted_values():
    assert vdot(5000, 1200) == pytest.approx(49.8, abs=0.1)  # Daniels: 20:00 5K -> 49.8
    assert 3 * 3600 + 10 * 60 < time_for_vdot(50, 42195) < 3 * 3600 + 11 * 60 + 30  # about 3:10:49
    assert time_for_vdot(vdot(10000, 2400), 10000) == pytest.approx(2400, abs=1)  # round trip


def test_riegel_math():
    assert riegel(1200, 5000, 10000, 1.06) == pytest.approx(1200 * 2 ** 1.06)
    assert fmt_time(3661) == "1:01:01" and fmt_time(75) == "1:15"


def test_ols_recovers_an_exact_power_law():
    ds = [3000, 5000, 10000, 21097.5]
    ts = [0.25 * d ** 1.09 for d in ds]
    fit = ols([math.log(d) for d in ds], [math.log(t) for t in ts])
    assert fit["slope"] == pytest.approx(1.09, abs=1e-9) and fit["r2"] == pytest.approx(1.0)


def mk_effort(d, t, days_ago=10, used=True, aid=1, now=None):
    now = now or datetime.now(UTC)
    return {"activity_id": aid, "date": (now - timedelta(days=days_ago)).isoformat(), "name": f"Run {d}",
            "sport": "running", "kind": "road", "distance_m": d, "time_s": t, "pace_s_per_km": t / (d / 1000),
            "avg_hr": 150, "ascent_m": 10, "flags": [], "used": used, "not_used_because": []}


def power_law_efforts(k=1.08, c=0.13, dists=(1000, 3000, 5000, 10000, 21097.5)):
    return [mk_effort(d, c * d ** k, aid=i + 1) for i, d in enumerate(dists)]


def test_predict_target_shows_the_math_and_a_headline():
    effs = power_law_efforts()
    out = predict.predict_target("marathon", "Marathon", 42195.0, effs)
    ids = {m["id"]: m for m in out["methods"]}
    assert set(ids) == {"riegel_106", "riegel_fit", "critical_speed", "vdot", "riegel_115"}
    # the fitted exponent finds the 1.08 we generated and the steps show substituted numbers
    assert ids["riegel_fit"]["k"] == pytest.approx(1.08, abs=1e-6)
    assert "1.080" in " ".join(ids["riegel_fit"]["steps"])
    steps = " ".join(ids["riegel_106"]["steps"])
    assert "21097.5" in steps and "42195.0" in steps and "^1.06" in steps
    # nearest effort for the marathon is the half
    assert ids["riegel_106"]["source_effort"]["distance_m"] == 21097.5
    # critical speed is outside its range at marathon time, so it is shown but not counted
    assert ids["critical_speed"]["status"] == "reference_only"
    h = out["headline"]
    assert h["low_s"] <= h["middle_s"] <= h["high_s"] and "median" in h["how"]
    assert "Critical speed" not in h["how"].split("Range")[0]
    assert out["support"]["level"] == "extrapolated" and out["support"]["ratio"] == pytest.approx(2.0)
    assert out["actual_best"] is None


def test_support_levels_and_missing_data():
    short = [mk_effort(5000, 1300)]
    assert predict.predict_target("marathon", "Marathon", 42195.0, short)["support"]["level"] == "weak"
    assert predict.predict_target("10k", "10K", 10000.0, short)["support"]["level"] == "extrapolated"  # 2x
    assert predict.predict_target("half", "Half", 21097.5, [mk_effort(15000, 4800)])["support"]["level"] == "good"  # 1.4x
    none = predict.predict_target("5k", "5K", 5000.0, [])
    assert none["headline"] is None and "No usable efforts" in none["notes"][0]
    only_target = predict.predict_target("5k", "5K", 5000.0, [mk_effort(5000, 1300)])
    assert only_target["headline"] is None and only_target["actual_best"]["time_s"] == 1300


def test_not_enough_data_is_explained_not_hidden():
    out = predict.predict_target("10k", "10K", 10000.0, [mk_effort(5000, 1300), mk_effort(21097.5, 6100)])
    fit = next(m for m in out["methods"] if m["id"] == "riegel_fit")
    assert fit["status"] == "not_enough_data" and "at least 3" in fit["steps"][0]


def test_unused_efforts_are_ignored():
    effs = power_law_efforts()
    five = next(e for e in effs if e["distance_m"] == 5000)
    five["used"] = False
    best = predict.best_per_distance(effs)
    assert 5000 not in best and 10000 in best


# ------------------------------------------------------------------ database + API
def insert_run(conn, aid, sport, start, dist_time, kind_sample=None):
    conn.execute("INSERT INTO activities (id, source, source_id, start_time, sport, name, distance_m, duration_s, "
                 "has_samples, created_at) VALUES (?, 'garmin', ?, ?, ?, ?, 1, 1, 1, 'x')",
                 (aid, str(aid), start, sport, f"Run {aid}"))
    for d, t in dist_time:
        conn.execute("INSERT INTO best_efforts (activity_id, distance_m, time_s, start_offset_s, avg_hr, ascent_m, gap_s) "
                     "VALUES (?, ?, ?, 0, 150, 5, 0)", (aid, d, t))
        conn.execute("INSERT INTO best_efforts_gap (activity_id, distance_m, time_s, start_offset_s, avg_hr, ascent_m, "
                     "gap_s, covered_m) VALUES (?, ?, ?, 0, 150, 5, 0, ?)", (aid, d, t, d))


@pytest.fixture
def seeded(authed, settings):
    conn = db.connect(settings.db_path)
    now = datetime.now(UTC)
    day = lambda n: (now - timedelta(days=n)).isoformat()  # noqa: E731
    k, c = 1.07, 0.27
    insert_run(conn, 101, "running", day(40), [(d, c * d ** k) for d in (3000, 5000, 10000)])
    insert_run(conn, 102, "running", day(20), [(d, c * 0.99 * d ** k) for d in (5000, 10000, 21097.5)])
    insert_run(conn, 103, "treadmill_running", day(5), [(5000, 1000)])  # absurdly fast, indoor
    conn.commit()
    conn.close()
    return authed


def test_api_requires_login(client):
    assert client.get("/api/predictions").status_code == 401


def test_api_predictions_end_to_end(seeded):
    r = seeded.get("/api/predictions?include_indoor=false").json()
    assert r["mission"].startswith("Use your data to train smarter")
    keys = [t["key"] for t in r["targets"]]
    assert keys == ["5k", "10k", "half", "marathon"]
    half = next(t for t in r["targets"] if t["key"] == "half")
    assert half["actual_best"]["activity_id"] == 102 and half["headline"]
    five = next(t for t in r["targets"] if t["key"] == "5k")
    # the indoor 5K at 16:40 is left out by default, and the response says why
    indoor = [e for e in r["efforts"] if e["activity_id"] == 103][0]
    assert indoor["used"] is False and "treadmill" in indoor["not_used_because"][0]
    assert five["actual_best"]["activity_id"] != 103
    default = seeded.get("/api/predictions").json()  # treadmill, trail and grade adjustment are on by default
    assert default["settings"] == {"window_days": 365, "include_indoor": True, "include_trail": True, "use_gap": True}
    assert next(e for e in default["efforts"] if e["activity_id"] == 103)["used"] is True
    assert default["gap_model"]["table"] and "Minetti" in default["gap_model"]["name"]
    assert {c["id"] for c in r["citations"]} >= {"riegel1981", "daniels1979", "poole2016", "minetti2002"}
    assert r["context"]["weeks"] == 8 and r["caveats"]
    assert "scan" in r


def test_api_toggles_and_exclusions_change_the_result(seeded):
    base = seeded.get("/api/predictions?include_indoor=false").json()
    ten = next(t for t in base["targets"] if t["key"] == "10k")
    seeded.post("/api/efforts/102/exclude")
    after = seeded.get("/api/predictions?include_indoor=false").json()
    ten2 = next(t for t in after["targets"] if t["key"] == "10k")
    assert ten2["actual_best"]["activity_id"] == 101 and ten2["actual_best"]["time_s"] != ten["actual_best"]["time_s"]
    assert all(e["used"] is False for e in after["efforts"] if e["activity_id"] == 102)
    seeded.delete("/api/efforts/102/exclude")
    assert seeded.get("/api/predictions?include_indoor=false").json()["targets"][1]["actual_best"]["activity_id"] == 102
    with_indoor = seeded.get("/api/predictions?include_indoor=true").json()
    five = next(t for t in with_indoor["targets"] if t["key"] == "5k")
    assert five["actual_best"]["activity_id"] == 103  # the 16:40 treadmill 5K is now the fastest
    assert seeded.post("/api/efforts/9999/exclude").status_code == 404


def test_backtest_is_near_zero_when_the_athlete_follows_the_formula(authed, settings):
    conn = db.connect(settings.db_path)
    now = datetime.now(UTC)
    aid = 200
    for week in range(1, 14):  # every ~2 weeks for half a year: a 5K and a 10K following Riegel 1.06 exactly
        day = (now - timedelta(days=week * 14)).isoformat()
        c = 0.3
        insert_run(conn, aid, "running", day, [(5000, c * 5000 ** 1.06), (10000, c * 10000 ** 1.06)])
        aid += 1
    conn.commit()
    conn.close()
    ten = next(t for t in authed.get("/api/predictions?window_days=730").json()["targets"] if t["key"] == "10k")
    s = ten["backtest"]["summary"]["riegel_106"]
    assert s["n"] >= 3 and abs(s["median_error_pct"]) < 0.5
    assert "optimistic" in ten["backtest"]["how"]


def test_scanner_computes_efforts_from_stored_samples(authed, settings):
    conn = db.connect(settings.db_path)
    conn.execute("INSERT INTO activities (id, source, source_id, start_time, sport, name, distance_m, duration_s, "
                 "has_samples, created_at) VALUES (300, 'garmin', '300', ?, 'running', 'Long', 12000, 3243, 1, 'x')",
                 (datetime.now(UTC).isoformat(),))
    t, d = run_samples([(12000, 3.7)])
    conn.executemany("INSERT INTO samples (activity_id, t, dist, hr) VALUES (300, ?, ?, 150)",
                     [(1_700_000_000 + int(x), y) for x, y in zip(t, d, strict=True)])
    conn.commit()
    assert efforts.pending(conn) == [300]
    scanner = efforts.EffortScanner(Settings(data_dir=settings.data_dir))
    scanner.run_blocking()
    rows = {r["distance_m"]: r["time_s"] for r in conn.execute("SELECT distance_m, time_s FROM best_efforts WHERE activity_id=300")}
    assert rows[5000.0] == pytest.approx(5000 / 3.7, abs=1.5) and 21097.5 not in rows
    assert efforts.pending(conn) == [] and scanner.done == 1
    conn.close()
