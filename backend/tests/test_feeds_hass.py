"""Home Assistant history feed: pulls history, writes series + daily."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import httpx

from app import db
from app.config import Settings
from app.feeds import homeassistant


def _settings(tmp_path):
    token_file = tmp_path / "hass_token"
    token_file.write_text("fake-token")
    return Settings(data_dir=tmp_path, request_delay_s=0,
                    hass_token_file=token_file,
                    hass_base_url="http://ha.test")


def test_writes_series_and_daily(tmp_path):
    s = _settings(tmp_path)
    db.init_db(s.db_path)
    conn = db.connect(s.db_path)
    target_day = date(2026, 10, 1)
    # Build payload at UTC 22:00 → 08:00 next day
    base = datetime.combine(target_day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=22)
    temp_series = [{
        "entity_id": "sensor.bedroom_temperature",
        "last_changed": (base + timedelta(hours=i)).isoformat(),
        "state": str(19.0 + i * 0.1),
    } for i in range(6)]
    rh_series = [{
        "entity_id": "sensor.bedroom_humidity",
        "last_changed": (base + timedelta(hours=i)).isoformat(),
        "state": str(55.0 + i * 0.5),
    } for i in range(6)]
    presence = [
        {"entity_id": "binary_sensor.bedroom_occupancy",
         "last_changed": (base + timedelta(hours=0)).isoformat(),
         "state": "on"},
        {"entity_id": "binary_sensor.bedroom_occupancy",
         "last_changed": (base + timedelta(hours=8)).isoformat(),
         "state": "off"},
    ]

    def handler(request):
        assert request.headers["Authorization"] == "Bearer fake-token"
        return httpx.Response(200, json=[temp_series, rh_series, presence])

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        stats = homeassistant.sync(conn, s, day=target_day, client=client)
    assert stats.series_rows == 12   # 6 temp + 6 rh (presence 'on/off' aren't floats)
    assert stats.daily_rows == 1
    row = conn.execute(
        "SELECT bedroom_temp_c_night, bedroom_rh_pct_night, bed_in_time, bed_out_time "
        "FROM ha_daily WHERE day = ?", (target_day.isoformat(),),
    ).fetchone()
    assert 19.0 < row["bedroom_temp_c_night"] < 20.0
    assert row["bed_in_time"] is not None
    assert row["bed_out_time"] is not None


def test_disabled_without_token(tmp_path):
    s = Settings(data_dir=tmp_path, request_delay_s=0)
    db.init_db(s.db_path)
    conn = db.connect(s.db_path)
    assert homeassistant.sync(conn, s).series_rows == 0
