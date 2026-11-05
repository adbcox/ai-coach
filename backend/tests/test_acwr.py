"""ACWR 7/28: a soft guide only (D5). Must be None until 28 days of history."""

from datetime import UTC, datetime

from app import db
from app.coach_maths import load as cm_load
from app.config import Settings


def _conn(tmp_path):
    s = Settings(data_dir=tmp_path, request_delay_s=0)
    db.init_db(s.db_path)
    return db.connect(s.db_path)


def test_acwr_none_until_28_days():
    assert cm_load._acwr([100.0] * 14) is None
    assert cm_load._acwr([100.0] * 27) is None
    assert cm_load._acwr([100.0] * 28) == 1.0


def test_acwr_spikes_when_last_week_jumps():
    series = [50.0] * 21 + [150.0] * 7     # acute 150, chronic 75 → 2.0
    v = cm_load._acwr(series)
    assert v is not None and 1.9 < v < 2.1


def test_acwr_0_28_from_live_table_before_enough_days(tmp_path):
    conn = _conn(tmp_path)
    for day in ("2026-11-01", "2026-11-02", "2026-11-03"):
        conn.execute(
            "INSERT INTO training_load_day (day, trimp, tss, ctl, atl, tsb, acwr, computed_at) "
            "VALUES (?, 0, 50, 10, 10, 0, NULL, ?)",
            (day, datetime.now(UTC).isoformat(timespec='seconds')),
        )
    conn.commit()
    assert cm_load.acwr_7_28(conn) is None
