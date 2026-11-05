"""life_signal_day: merges calendar + checkin into one day row."""

from __future__ import annotations

from datetime import date

from app import db
from app.config import Settings
from app.feeds import life_signal


def _conn(tmp_path):
    s = Settings(data_dir=tmp_path, request_delay_s=0)
    db.init_db(s.db_path)
    return db.connect(s.db_path)


def test_travel_day_flagged(tmp_path):
    conn = _conn(tmp_path)
    conn.execute(
        "INSERT INTO calendar_events (id, day, start_time, end_time, summary, "
        "is_travel, is_busy, source, fetched_at) "
        "VALUES ('x', '2026-11-04', '2026-11-04T12:00:00+00:00', "
        "'2026-11-04T15:00:00+00:00', 'Flight', 1, 1, 'ics', '2026-11-05T00:00:00+00:00')",
    )
    conn.commit()
    life_signal.recompute_range(conn, start=date(2026, 11, 4), end=date(2026, 11, 4))
    row = conn.execute(
        "SELECT travel, busy, sick FROM life_signal_day WHERE day = '2026-11-04'"
    ).fetchone()
    assert row["travel"] == 1
    assert row["sick"] == 0


def test_sick_day_from_checkin(tmp_path):
    conn = _conn(tmp_path)
    conn.execute(
        "INSERT INTO checkins (day, overall, legs, ill, note, created_at) "
        "VALUES ('2026-11-04', 2, 2, 1, 'flu', '2026-11-05T00:00:00+00:00')",
    )
    conn.commit()
    life_signal.recompute_range(conn, start=date(2026, 11, 4), end=date(2026, 11, 4))
    row = conn.execute(
        "SELECT sick, note FROM life_signal_day WHERE day = '2026-11-04'"
    ).fetchone()
    assert row["sick"] == 1
    assert row["note"] == "flu"


def test_empty_day_writes_nothing(tmp_path):
    conn = _conn(tmp_path)
    rows_written = life_signal.recompute_range(conn, start=date(2026, 11, 4),
                                               end=date(2026, 11, 4))
    assert rows_written == 0
    assert conn.execute("SELECT COUNT(*) FROM life_signal_day").fetchone()[0] == 0
