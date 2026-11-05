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
                backfill_rate_halving=True, request_delay_s=0,
                # start == end disables the window gate (always open) so these
                # tests don't depend on wall-clock time.
                backfill_window_start="00:00", backfill_window_end="00:00")
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


# ---------- carry-over delay (env floor beats stale stored) ----------

def test_load_lifts_stale_delay_to_env_floor(conn):
    from app.wellness import set_state
    # stored (pre-upgrade) value is 3s; new env floor is 10s.
    set_state(conn, "throttle.current_delay_s", "3.000")
    s = _settings(backfill_delay_s=10.0)
    t = GarminThrottle(s)
    t.load(conn)
    assert t.snapshot(conn).current_delay_s == 10.0


def test_load_keeps_burst_doubled_value_above_env(conn):
    from app.wellness import set_state
    set_state(conn, "throttle.current_delay_s", "20.000")  # post-429 doubled
    s = _settings(backfill_delay_s=10.0)
    t = GarminThrottle(s)
    t.load(conn)
    assert t.snapshot(conn).current_delay_s == 20.0


# ---------- nightly window ----------

def test_window_closed_raises_outside_window(conn):
    from app.garmin_throttle import OutsideWindow
    # 23:00-06:00 NYC; freeze clock to noon NYC = 17:00 UTC -> closed.
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo
    noon_nyc = datetime(2026, 11, 5, 12, 0, tzinfo=ZoneInfo("America/New_York")).astimezone(UTC)
    s = _settings(backfill_delay_s=0.0, backfill_window_start="23:00",
                  backfill_window_end="06:00", backfill_window_tz="America/New_York")
    t = GarminThrottle(s)
    t.load(conn)
    import app.garmin_throttle as mod
    class _FixedClock:
        def __init__(self, when): self.when = when
        def __call__(self): return self.when
    # Patch "now" by monkeypatching datetime.now inside the helper.
    import datetime as _dt
    class _FakeDT(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return noon_nyc if tz is None else noon_nyc.astimezone(tz)
    mod_dt = mod.datetime
    mod.datetime = _FakeDT
    try:
        with pytest.raises(OutsideWindow):
            t.before_request(conn, kind="search")
    finally:
        mod.datetime = mod_dt


def test_window_open_at_midnight_nyc_allows_requests(conn):
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo
    import app.garmin_throttle as mod
    import datetime as _dt
    midnight_nyc = datetime(2026, 11, 5, 0, 30, tzinfo=ZoneInfo("America/New_York")).astimezone(UTC)
    s = _settings(backfill_delay_s=0.0, backfill_window_start="23:00",
                  backfill_window_end="06:00", backfill_window_tz="America/New_York")
    t = GarminThrottle(s)
    t.load(conn)
    class _FakeDT(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return midnight_nyc if tz is None else midnight_nyc.astimezone(tz)
    mod_dt = mod.datetime
    mod.datetime = _FakeDT
    try:
        t.before_request(conn, kind="search")  # must NOT raise
    finally:
        mod.datetime = mod_dt
    assert t.snapshot(conn).day_count == 1


def test_run_pauses_cleanly_when_window_closes_midstream(conn):
    """Simulate an in-flight backfill: a request succeeds while the window is
    open, then the clock crosses 06:00 and the next before_request raises
    OutsideWindow — the throttle state (day_count, last_request_ts) is
    preserved so the backfill can resume the next night."""
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo
    from app.garmin_throttle import OutsideWindow
    import app.garmin_throttle as mod
    import datetime as _dt
    s = _settings(backfill_delay_s=0.0, backfill_window_start="23:00",
                  backfill_window_end="06:00", backfill_window_tz="America/New_York")
    t = GarminThrottle(s)
    t.load(conn)
    before_close = datetime(2026, 11, 5, 5, 59, tzinfo=ZoneInfo("America/New_York")).astimezone(UTC)
    after_close = datetime(2026, 11, 5, 6, 1, tzinfo=ZoneInfo("America/New_York")).astimezone(UTC)
    class _DT1(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return before_close if tz is None else before_close.astimezone(tz)
    class _DT2(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return after_close if tz is None else after_close.astimezone(tz)
    mod_dt = mod.datetime
    mod.datetime = _DT1
    try:
        t.before_request(conn, kind="download")  # in-window, succeeds
        snap = t.snapshot(conn)
        assert snap.day_count == 1
        last_ts = snap.last_request_ts
        mod.datetime = _DT2
        with pytest.raises(OutsideWindow):
            t.before_request(conn, kind="download")
        # State preserved for resume
        snap2 = t.snapshot(conn)
        assert snap2.day_count == 1
        assert snap2.last_request_ts == last_ts
    finally:
        mod.datetime = mod_dt
