import json
import re

from app import db, diagnostics
from app.wellness import has_data, is_empty

# Shapes taken from a real Garmin account (structure only).


def test_days_full_of_nulls_count_as_empty():
    null_sleep = {"calendarDate": None, "sleepTimeSeconds": None, "deviceRemCapable": False,
                  "retro": False, "sleepScores": None}
    assert not is_empty(null_sleep)            # generic check is fooled by the booleans...
    assert not has_data("sleep", null_sleep)   # ...the per-type check is not
    assert has_data("sleep", {"sleepTimeSeconds": 27000})
    assert not has_data("hrv", {"hrvSummary": {"lastNightAvg": None}, "hrvReadings": []})
    assert has_data("hrv", {"hrvSummary": {"lastNightAvg": 41}, "hrvReadings": []})
    assert not has_data("heart_rate", {"restingHeartRate": None, "heartRateValues": None})
    assert has_data("daily_summaries", {"data": [{"movement": {"steps": {"value": 5}}}]})
    assert not has_data("daily_summaries", {"data": [{"movement": {"steps": {"value": None}},
                                                      "heartRate": {"restingValue": None}}]})
    assert not has_data("body_battery", [{"charged": None, "bodyBatteryValueDescriptorDTOList": None}])
    assert has_data("body_battery", [{"charged": 40}])
    assert not has_data("steps", [{"totalSteps": None}])
    assert has_data("hrv_summaries", {"hrvSummaries": [{"lastNightAvg": None, "weeklyAvg": 44}]})
    assert not has_data("anything_else", None)
    assert has_data("anything_else", {"a": 1})


def test_stale_running_syncs_are_closed_on_startup(tmp_path):
    from app.config import Settings
    from app.main import create_app
    settings = Settings(data_dir=tmp_path)
    db.init_db(settings.db_path)
    conn = db.connect(settings.db_path)
    conn.execute("INSERT INTO sync_runs (provider, started_at, status, message) VALUES "
                 "('garmin', '2026-01-01T00:00:00+00:00', 'running', 'Health data: sleep back to 2024')")
    conn.commit()
    conn.close()
    create_app(settings, start_scheduler=False)
    conn = db.connect(settings.db_path)
    row = conn.execute("SELECT status, finished_at, message FROM sync_runs").fetchone()
    conn.close()
    assert row["status"] == "error" and row["finished_at"] and "interrupted" in row["message"]


def test_diagnostics_hides_ids_timestamps_and_body_measurements():
    shape = diagnostics.Shape()
    shape.add({"userProfilePk": 77800753, "ownerId": 77800753, "deviceId": 3448008758,
               "beginTimestamp": 1758635939000, "sleepStartTimestampGMT": 1776580385000,
               "calendarDate": "2026-10-30", "weight": 63502.0, "bodyFat": 12.5, "bmi": 19.1,
               "activityId": 22222222222, "averageHR": 152, "distance": 10234.5,
               "hrValuesArray": [[1758635939000, 60]]})
    text = json.dumps(shape.render())
    for secret in ("77800753", "3448008758", "1758635939000", "1776580385000", "63502", "12.5", "19.1",
                   "22222222222", "2026-10-30"):
        assert secret not in text, secret
    assert re.search(r'"\$.averageHR".*?"range": \[\s*152', text, re.S)
    assert "10234.5" in text
    assert '"$.userProfilePk"' in text  # the field itself is still described


def test_recovery_endpoint_parses_real_shapes(tmp_path):
    import httpx
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.garmin.client import GarminClient
    from app.main import create_app
    from tests.conftest import FakeGarmin
    fake = FakeGarmin()
    settings = Settings(data_dir=tmp_path, request_delay_s=0)
    app = create_app(settings, lambda k, u: GarminClient(k, u, transport=httpx.MockTransport(fake.handler)),
                     start_scheduler=False)
    today = __import__("datetime").date.today().isoformat()
    conn = db.connect(settings.db_path)
    ins = ("INSERT INTO wellness_raw (source, kind, start_date, end_date, fetched_at, is_empty, payload) "
           "VALUES ('garmin', ?, ?, ?, 'x', 0, ?)")
    conn.execute(ins, ("sleep", today, today, json.dumps({
        "calendarDate": today, "sleepTimeSeconds": 27000, "deepSleepSeconds": 5400,
        "remSleepSeconds": 5400, "lightSleepSeconds": 14400, "awakeSleepSeconds": 1800,
        "avgHeartRate": 49, "avgSleepStress": 18, "sleepNeed": {"actual": 480},
        "sleepScores": {"overall": {"value": 82}}})))
    conn.execute(ins, ("hrv_summaries", today, today, json.dumps({"hrvSummaries": [{
        "calendarDate": today, "lastNightAvg": 44, "weeklyAvg": 46, "status": "BALANCED",
        "baseline": {"balancedLow": 40, "balancedUpper": 58}}]})))
    conn.execute(ins, ("daily_summaries", today, today, json.dumps({"data": [{
        "calendarDate": today, "heartRate": {"restingValue": 47},
        "bodyBattery": {"maxValue": 92, "minValue": 21, "chargedValue": 70, "drainedValue": 71},
        "stress": {"avgLevel": 24}, "movement": {"steps": {"value": 11000}},
        "intensityMinutes": {"moderate": 20, "vigorous": 10}, "respiration": {"avgValue": 14},
        "pulseOx": {"avgValue": 96}}]})))
    conn.commit()
    conn.close()
    with TestClient(app, headers={"X-Requested-With": "aec"}) as c:
        assert c.get("/api/recovery").status_code == 401
        c.post("/api/setup", json={"username": "admin", "password": "correct horse battery"})
        day = c.get("/api/recovery?days=30").json()["days"][-1]
        assert day["date"] == today
        assert day["sleep_score"] == 82 and day["sleep_h"] == 7.5 and day["deep_h"] == 1.5
        assert day["hrv"] == 44 and day["hrv_weekly"] == 46 and day["hrv_low"] == 40 and day["hrv_high"] == 58
        assert day["resting_hr"] == 47 and day["bb_max"] == 92 and day["stress_avg"] == 24
        assert day["steps"] == 11000 and day["intensity_min"] == 40  # vigorous counts double
        assert c.get("/api/health").json()["version"] == "0.2.0"
