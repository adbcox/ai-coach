"""Weather feed: fetches archive, picks nearest hour, upserts rows.

Uses httpx.MockTransport so no network call is made.
"""

from __future__ import annotations

import json

import httpx

from app import db
from app.config import Settings
from app.feeds import weather


_HOURLY_PAYLOAD = {
    "hourly": {
        "time": [
            "2026-10-01T09:00",
            "2026-10-01T10:00",
            "2026-10-01T11:00",
        ],
        "temperature_2m": [12.0, 14.0, 16.0],
        "apparent_temperature": [10.0, 12.0, 15.0],
        "dew_point_2m": [5.0, 6.0, 7.0],
        "relative_humidity_2m": [60.0, 55.0, 50.0],
        "wind_speed_10m": [2.0, 3.0, 4.0],
        "precipitation": [0.0, 0.0, 0.1],
    },
}
_DAILY_PAYLOAD = {
    "daily": {
        "temperature_2m_min": [10.0],
        "temperature_2m_max": [17.0],
        "apparent_temperature_mean": [12.5],
        "dew_point_2m_mean": [6.0],
        "relative_humidity_2m_mean": [55.0],
        "precipitation_sum": [0.1],
    },
}


def _mock(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _settings(tmp_path):
    return Settings(data_dir=tmp_path, request_delay_s=0,
                    home_latitude=38.9, home_longitude=-77.0)


def test_disabled_without_coords(tmp_path):
    s = Settings(data_dir=tmp_path, request_delay_s=0)
    db.init_db(s.db_path)
    conn = db.connect(s.db_path)
    stats = weather.backfill_pending(conn, s)
    assert stats.activity_rows == 0


def test_picks_nearest_hour(tmp_path):
    s = _settings(tmp_path)
    db.init_db(s.db_path)
    conn = db.connect(s.db_path)
    conn.execute(
        "INSERT INTO activities (source, source_id, start_time, created_at) "
        "VALUES ('garmin', '1', '2026-10-01T10:20:00+00:00', '2026-11-05T00:00:00+00:00')"
    )
    conn.commit()

    def handler(request):
        assert "latitude=38.9" in str(request.url)
        return httpx.Response(200, json=_HOURLY_PAYLOAD)

    with _mock(handler) as client:
        stats = weather.backfill_pending(conn, s, client=client)
    assert stats.activity_rows == 1
    row = conn.execute(
        "SELECT temp_c, feels_like_c, dew_point_c, humidity_pct, "
        "       wind_m_s, precip_mm FROM activity_weather WHERE activity_id = 1"
    ).fetchone()
    # Nearest to 10:20 is the 10:00 bucket.
    assert row["temp_c"] == 14.0
    assert row["feels_like_c"] == 12.0


def test_refresh_day_upserts_weather_day(tmp_path):
    from datetime import date
    s = _settings(tmp_path)
    db.init_db(s.db_path)
    conn = db.connect(s.db_path)

    def handler(request):
        assert "daily=" in str(request.url)
        return httpx.Response(200, json=_DAILY_PAYLOAD)

    with _mock(handler) as client:
        ok = weather.refresh_day(conn, s, date(2026, 10, 1), client=client)
    assert ok
    row = conn.execute(
        "SELECT temp_min_c, temp_max_c, humidity_mean_pct, precip_mm "
        "FROM weather_day WHERE day = '2026-10-01'"
    ).fetchone()
    assert row["temp_min_c"] == 10.0
    assert row["precip_mm"] == 0.1


def test_backfill_is_idempotent(tmp_path):
    s = _settings(tmp_path)
    db.init_db(s.db_path)
    conn = db.connect(s.db_path)
    conn.execute(
        "INSERT INTO activities (source, source_id, start_time, created_at) "
        "VALUES ('garmin', '1', '2026-10-01T10:20:00+00:00', '2026-11-05T00:00:00+00:00')"
    )
    conn.commit()

    def handler(request):
        return httpx.Response(200, json=_HOURLY_PAYLOAD)

    with _mock(handler) as client:
        stats1 = weather.backfill_pending(conn, s, client=client)
        stats2 = weather.backfill_pending(conn, s, client=client)
    assert stats1.activity_rows == 1
    assert stats2.activity_rows == 0
