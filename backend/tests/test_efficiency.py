"""Efficiency factor — Friel 2012."""

from app.coach_maths.efficiency import ef_bike, ef_run


def test_ef_bike_is_np_over_hr():
    assert abs(ef_bike(np=200, avg_hr=150) - (200 / 150)) < 1e-9


def test_ef_bike_rejects_zero_or_missing():
    assert ef_bike(np=0, avg_hr=150) is None
    assert ef_bike(np=200, avg_hr=None) is None
    assert ef_bike(np=200, avg_hr=35) is None


def test_ef_run_higher_when_faster_or_lower_hr():
    base = ef_run(ngp_m_s=3.0, avg_hr=150)
    faster = ef_run(ngp_m_s=3.3, avg_hr=150)
    lowhr = ef_run(ngp_m_s=3.0, avg_hr=140)
    assert faster > base and lowhr > base
