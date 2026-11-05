"""Smoke tests for the backfill throttle (dispatch-05 P1).

The throttle must:
- enforce the min-spacing delay (sleep when calls arrive too close)
- enforce the daily cap (raise ThrottlePaused once the cap is reached)
- raise ThrottlePaused while a pause window is active
- halve the rate (double the delay) after a burst, when configured
"""

from __future__ import annotations

import time

import pytest

from app import db
from app.config import Settings
from app.garmin_throttle import GarminThrottle, ThrottlePaused


@pytest.fixture
def conn(tmp_path):
    settings = Settings(data_dir=tmp_path, request_delay_s=0)
    db.init_db(settings.db_path)
    c = db.connect(settings.db_path)
    yield c
    c.close()


def _settings(**over) -> Settings:
    base = dict(backfill_delay_s=0.0, backfill_daily_cap=5, backfill_pause_hours=0.01,
                backfill_rate_halving=True, request_delay_s=0)
    base.update(over)
    return Settings(data_dir=__import__("pathlib").Path("/tmp/ignored"), **base)


def test_spacing_sleeps_between_requests(conn, monkeypatch):
    s = _settings(backfill_delay_s=0.05)
    t = GarminThrottle(s)
    t.load(conn)
    start = time.monotonic()
    for _ in range(3):
        t.before_request(conn, kind="search")
    elapsed = time.monotonic() - start
    # three spaced calls should take at least 2 * delay (first is free)
    assert elapsed >= 0.08


def test_daily_cap_raises_and_persists(conn):
    s = _settings(backfill_delay_s=0.0, backfill_daily_cap=3)
    t = GarminThrottle(s)
    t.load(conn)
    for _ in range(3):
        t.before_request(conn, kind="search")
    with pytest.raises(ThrottlePaused) as exc:
        t.before_request(conn, kind="search")
    assert "daily cap" in str(exc.value).lower()
    # a fresh instance must see the cap state (persistence)
    t2 = GarminThrottle(s)
    t2.load(conn)
    with pytest.raises(ThrottlePaused):
        t2.before_request(conn, kind="search")


def test_hit_burst_pauses_and_halves(conn):
    s = _settings(backfill_delay_s=0.1, backfill_pause_hours=1.0, backfill_rate_halving=True)
    t = GarminThrottle(s)
    t.load(conn)
    t.before_request(conn, kind="search")  # one real request
    t.hit_burst(conn, 429)
    # pause window is now active
    with pytest.raises(ThrottlePaused) as exc:
        t.before_request(conn, kind="search")
    assert "429" in str(exc.value) or "paused" in str(exc.value).lower()
    snap = t.snapshot(conn)
    assert snap.pause_until_ts > time.time() + 3000  # ~1h ahead
    assert snap.current_delay_s >= 0.2  # halved rate = doubled delay


def test_resume_after_pause_uses_persisted_state(conn):
    s = _settings(backfill_delay_s=0.0, backfill_pause_hours=0.0)  # pause instantly expires
    t = GarminThrottle(s)
    t.load(conn)
    t.hit_burst(conn, 503)
    # pause is in the past, so a fresh request goes through
    time.sleep(0.01)
    t2 = GarminThrottle(s)
    t2.load(conn)
    t2.before_request(conn, kind="search")  # must not raise
    snap = t2.snapshot(conn)
    assert snap.day_count == 1


def test_snapshot_reports_cap_from_settings(conn):
    s = _settings(backfill_daily_cap=1234)
    t = GarminThrottle(s)
    t.load(conn)
    assert t.snapshot(conn).daily_cap == 1234
