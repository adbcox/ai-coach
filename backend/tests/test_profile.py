import json

from app import body
from app.db import connect, init_db


def put_weight(conn, payload, start="2026-10-01", end="2026-10-31"):
    conn.execute("INSERT OR REPLACE INTO wellness_raw (source, kind, start_date, end_date, fetched_at, is_empty, payload) "
                 "VALUES ('garmin','weight',?,?,'2026-11-01',0,?)", (start, end, json.dumps(payload)))
    conn.commit()


def test_kg_conversion_and_limits():
    assert body._kg(63502.0) == 63.5
    assert body._kg(71.2) == 71.2
    assert body._kg(0) is None and body._kg(None) is None and body._kg(5) is None


def test_weight_history_reads_the_known_places(tmp_path):
    init_db(tmp_path / "t.db")
    conn = connect(tmp_path / "t.db")
    put_weight(conn, {"dailyWeightSummaries": [
        {"summaryDate": "2026-10-28", "latestWeight": {"weight": 64000.0}},
        {"summaryDate": "2026-10-30", "allWeightMetrics": [{"weight": 63900.0}, {"weight": 63502.0}]},
        {"summaryDate": "2026-10-31", "minWeight": 63400.0, "maxWeight": 63600.0},
        {"summaryDate": "2026-11-01", "latestWeight": {"weight": None}},
    ]})
    hist = body.weight_history(conn)
    assert hist == [{"date": "2026-10-28", "kg": 64.0}, {"date": "2026-10-30", "kg": 63.5}, {"date": "2026-10-31", "kg": 63.6}]
    assert body.latest_garmin_weight(conn) == {"kg": 63.6, "date": "2026-10-31"}


def test_no_weight_data(tmp_path):
    init_db(tmp_path / "t.db")
    conn = connect(tmp_path / "t.db")
    assert body.latest_garmin_weight(conn) is None


def test_profile_through_the_api(authed):
    client = authed
    r = client.get("/api/preferences").json()
    assert r["sex"] is None and r["weight_kg"] is None and r["weight_source"] is None
    r = client.put("/api/preferences", json={"sex": "female", "weight_kg": 61.5, "birth_year": 1990}).json()
    assert r["sex"] == "female" and r["weight_kg"] == 61.5 and r["weight_source"] == "custom" and r["age"] is not None
    r = client.put("/api/preferences", json={"weight_kg": None}).json()
    assert r["weight_source"] is None
    bad = client.put("/api/preferences", json={"sex": "robot"})
    assert bad.status_code == 400


def test_garmin_weight_is_used_until_a_custom_value_is_set(authed):
    conn = connect(authed.app.state.settings.db_path)
    put_weight(conn, {"dailyWeightSummaries": [{"summaryDate": "2026-10-30", "latestWeight": {"weight": 63502.0}}]})
    r = authed.get("/api/preferences").json()
    assert r["weight_kg"] == 63.5 and r["weight_source"] == "garmin" and r["weight_garmin_date"] == "2026-10-30"
    r = authed.put("/api/preferences", json={"weight_kg": 70}).json()
    assert r["weight_kg"] == 70 and r["weight_source"] == "custom" and r["weight_garmin_kg"] == 63.5
    assert authed.get("/api/weight").json()["history"] == [{"date": "2026-10-30", "kg": 63.5}]
