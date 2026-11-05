"""TRIMP (Banister) — the HR-weighted load that hrTSS is normalised against."""

from app.coach_maths.load import hrtss, trimp


def test_trimp_scales_with_duration():
    a = trimp(duration_s=1800, avg_hr=150, lthr=160, max_hr=190)
    b = trimp(duration_s=3600, avg_hr=150, lthr=160, max_hr=190)
    assert a and b and 1.95 < (b / a) < 2.05   # exactly double


def test_trimp_rises_with_intensity():
    easy = trimp(3600, 120, 160, 190)
    hard = trimp(3600, 170, 160, 190)
    assert easy and hard and hard > easy * 2


def test_trimp_missing_inputs_return_none():
    assert trimp(0, 150, 160, 190) is None
    assert trimp(3600, None, 160, 190) is None
    assert trimp(3600, 150, 160, None) is None


def test_hrtss_one_hour_at_lthr_is_about_100():
    tss, _ = hrtss(duration_s=3600, avg_hr=160, lthr=160, max_hr=190)
    assert tss is not None
    assert 95 < tss < 105
