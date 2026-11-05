"""Composite readiness 0-100 with re-normalising weights (REPORT-02 §3.4)."""

import json

from app import db
from app.coach_maths.readiness import (
    ReadinessParts,
    _checkin_part,
    _hrv_z_to_part,
    _load_part,
    _rhr_z_to_part,
    compose,
    recompute_today,
)
from app.config import Settings


def test_hrv_z_maps_to_sensible_band():
    assert _hrv_z_to_part(0.0) == 50
    assert _hrv_z_to_part(1.0) == 90
    assert _hrv_z_to_part(-1.0) == 10


def test_rhr_z_inverts():
    # low RHR is good → positive z (higher than baseline) is bad
    bad = _rhr_z_to_part(1.0)
    good = _rhr_z_to_part(-1.0)
    assert good is not None and bad is not None and good > bad


def test_ill_forces_red_zero():
    parts = ReadinessParts(hrv=90, sleep=90, rhr=90, load=90, checkin=90, ill=True)
    score, band, _ = compose(parts)
    assert score == 0 and band == "red"


def test_missing_parts_renormalise():
    # only HRV known; score should be the HRV part alone
    parts = ReadinessParts(hrv=80, sleep=None, rhr=None, load=None, checkin=None)
    score, band, _ = compose(parts)
    assert score == 80 and band == "green"


def test_bands_boundaries():
    for score, want_band in ((65, "green"), (64, "amber"), (45, "amber"), (44, "red")):
        s, b, _ = compose(ReadinessParts(hrv=score, sleep=None, rhr=None, load=None,
                                         checkin=None))
        assert s == score and b == want_band


def test_checkin_overall_and_legs_average():
    assert _checkin_part(5, 5, False) == 100
    assert _checkin_part(1, 1, False) == 0
    assert _checkin_part(3, 3, False) == 50


def test_load_part_penalises_high_acwr():
    fresh_ok = _load_part(0.0, 1.0)
    acwr_high = _load_part(0.0, 1.8)
    assert fresh_ok is not None and acwr_high is not None
    assert acwr_high < fresh_ok


def test_recompute_today_persists(tmp_path):
    s = Settings(data_dir=tmp_path, request_delay_s=0)
    db.init_db(s.db_path)
    conn = db.connect(s.db_path)
    conn.execute(
        "INSERT INTO wellness_raw (source, kind, start_date, end_date, fetched_at, "
        "is_empty, payload) VALUES ('garmin', 'sleep', '2026-11-05', '2026-11-05', 'x', 0, ?)",
        (json.dumps({"sleepScores": {"overall": {"value": 82}}}),),
    )
    conn.commit()
    out = recompute_today(conn, today="2026-11-05")
    assert out["day"] == "2026-11-05"
    assert out["band"] in ("green", "amber", "red")
    row = conn.execute(
        "SELECT score, band FROM readiness_day WHERE day = '2026-11-05'",
    ).fetchone()
    assert row is not None
