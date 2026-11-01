import json
from datetime import UTC, datetime, timedelta

import pytest

from app import db, efforts, maxhr, predict, references
from tests.test_predictions import insert_run


def test_hr_peak_ignores_single_sample_spikes_and_uses_a_rolling_average():
    t = list(range(120))
    hr = [150.0] * 120
    hr[60] = 225.0                                  # one-sample optical glitch
    assert efforts.hr_peak(t, hr)["peak_hr"] == pytest.approx(150, abs=0.01)
    ramp = [150.0 + 35 * min(1, i / 60) for i in range(120)]  # climbs to 185 and holds
    assert efforts.hr_peak(t, ramp)["peak_hr"] == pytest.approx(185, abs=0.5)
    assert efforts.hr_peak([0, 1], [150, 150]) is None        # too little data
    assert efforts.hr_peak(t, [None] * 120) is None


def seed_peaks(conn, peaks, sport="running"):
    now = datetime.now(UTC)
    for i, p in enumerate(peaks):
        aid = 700 + i
        conn.execute("INSERT INTO activities (id, source, source_id, start_time, sport, name, has_samples, created_at) "
                     "VALUES (?, 'garmin', ?, ?, ?, ?, 1, 'x')", (aid, str(aid), (now - timedelta(days=10 + i)).isoformat(), sport, f"Run {i}"))
        conn.execute("INSERT INTO hr_peaks (activity_id, peak_hr, at_offset_s, samples) VALUES (?, ?, 100, 500)", (aid, p))
    conn.commit()


def test_max_hr_estimate_is_the_median_of_the_top_three_and_shows_its_working(authed, settings):
    conn = db.connect(settings.db_path)
    seed_peaks(conn, [186, 184, 183, 170, 162])
    est = maxhr.estimate(conn)
    assert est["estimate"] == 184 and est["confidence"] == "ok"
    assert any("median of those three" in s for s in est["steps"])
    assert est["top_peaks"][0]["peak_hr"] == 186
    conn.close()
    api = authed.get("/api/maxhr").json()
    assert api["estimate"] == 184 and {c["id"] for c in api["citations"]} == {"tanaka2001", "kasiak2023"}
    prefs = authed.get("/api/preferences").json()
    assert prefs["max_hr"] == 184 and prefs["max_hr_source"] == "auto"   # zones follow the robust estimate
    applied = authed.post("/api/maxhr/apply").json()
    assert applied["max_hr_source"] == "custom" and applied["max_hr"] == 184


def test_a_lone_glitchy_peak_cannot_set_the_maximum(authed, settings):
    conn = db.connect(settings.db_path)
    seed_peaks(conn, [214, 183, 182, 180])           # one implausible 214
    assert maxhr.estimate(conn)["estimate"] == 183   # the median of 214, 183, 182 -> 183
    conn.close()


def test_few_peaks_means_low_confidence_and_age_formula_is_only_a_comparison(authed, settings):
    conn = db.connect(settings.db_path)
    seed_peaks(conn, [181, 176])
    authed.put("/api/preferences", json={"birth_year": datetime.now(UTC).year - 40})
    est = maxhr.estimate(conn)
    assert est["confidence"] == "low" and est["estimate"] == 181
    assert est["age_formula_tanaka"] == 180 and "Tanaka" in " ".join(est["steps"])
    conn.close()
    assert authed.get("/api/maxhr").status_code == 200
    assert authed.post("/api/maxhr/apply").status_code == 200


def test_max_hr_apply_needs_data(authed):
    assert authed.post("/api/maxhr/apply").status_code == 400


def test_marked_races_become_the_back_test_anchors(authed, settings):
    conn = db.connect(settings.db_path)
    now = datetime.now(UTC)
    aid = 800
    for week in range(1, 8):
        day = (now - timedelta(days=week * 20)).isoformat()
        insert_run(conn, aid, "running", day, [(5000, 0.3 * 5000 ** 1.06 * (1.0 if week % 2 else 1.02)), (10000, 0.3 * 10000 ** 1.06)])
        aid += 1
    conn.commit()
    conn.close()
    base = next(t for t in authed.get("/api/predictions?window_days=730").json()["targets"] if t["key"] == "5k")
    assert base["backtest"]["basis"] == "local_bests" and base["backtest"]["races"] == []
    for a in (800, 802, 804):
        assert authed.post(f"/api/activities/{a}/race").status_code == 200
    assert authed.get("/api/activities/800").json()["is_race"] is True
    five = next(t for t in authed.get("/api/predictions?window_days=730").json()["targets"] if t["key"] == "5k")
    assert five["backtest"]["basis"] == "races" and "MARKED RACES" in five["backtest"]["how"]
    assert len(five["backtest"]["races"]) >= 1 and all(r["predictions"] for r in five["backtest"]["races"])
    authed.delete("/api/activities/800/race")
    assert authed.get("/api/activities/800").json()["is_race"] is False


def seed_resting_hr(conn, bpm=50, days=12):
    now = datetime.now(UTC)
    for k in range(days):
        d = (now - timedelta(days=k)).date().isoformat()
        payload = {"data": [{"calendarDate": d, "heartRate": {"restingValue": bpm}, "movement": {"steps": {"value": 5000}}}]}
        conn.execute("INSERT INTO wellness_raw (source, kind, start_date, end_date, fetched_at, is_empty, payload) VALUES "
                     "('garmin', 'daily_summaries', ?, ?, 'x', 0, ?)", (d, d, json.dumps(payload)))
    conn.commit()


def test_vo2max_methods_show_their_math_and_cite_known_sources(authed, settings):
    conn = db.connect(settings.db_path)
    now = datetime.now(UTC)
    insert_run(conn, 900, "running", (now - timedelta(days=20)).isoformat(), [(5000, 1200), (10000, 2520)])
    seed_resting_hr(conn, 50)
    conn.commit()
    conn.close()
    authed.put("/api/preferences", json={"max_hr": 190, "watch_vo2max": 55})
    d = authed.get("/api/vo2max").json()
    methods = {m["id"]: m for m in d["methods"]}
    assert methods["vdot"]["value"] == pytest.approx(predict.vdot(5000, 1200) / 2 + predict.vdot(10000, 2520) / 2, abs=0.05)
    assert methods["hr_ratio"]["value"] == pytest.approx(15.3 * 190 / 50)                    # 58.14
    assert methods["hr_ratio"]["low"] == pytest.approx(15.3 * 190 / 50 - 4.7)
    assert "15.3 x 190 / 50" in " ".join(methods["hr_ratio"]["steps"])
    assert d["watch"]["value"] == 55 and len(d["watch"]["differences"]) == 2
    assert "not a measured" in d["note"].lower() or "none of these is a measured" in d["note"].lower()
    ids = {r["id"] for r in references.REFERENCES}
    assert all(m["citation"] in ids for m in d["methods"]) and {c["id"] for c in d["citations"]} <= ids
    assert d["trend"] and d["trend"][-1]["vdot"] > 40


def test_vo2max_says_what_is_missing(authed):
    d = authed.get("/api/vo2max").json()
    assert all(m["status"] == "not_enough_data" and m["steps"] for m in d["methods"])
    assert authed.put("/api/preferences", json={"watch_vo2max": 5}).status_code == 422
