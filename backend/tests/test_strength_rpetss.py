"""Strength rpeTSS — RPE × minutes × 100/(7×60)."""

import math

from app.coach_maths.load import LoadInput, compute_activity_load, rpe_tss


def test_rpe_7_for_60_min_is_100():
    tss, _ = rpe_tss(duration_s=3600, rpe=7)
    assert tss is not None
    assert math.isclose(tss, 100.0, rel_tol=1e-3)


def test_rpe_zero_or_missing_returns_none():
    assert rpe_tss(3600, 0)[0] is None
    assert rpe_tss(3600, None)[0] is None


def test_dispatch_strength_family():
    li = LoadInput(activity_id=1, sport_key="strength_training", duration_s=2700,
                   distance_m=0, avg_hr=120, max_hr_user=190, ftp=None, lthr=None,
                   threshold_pace_s_per_m=None, css_s_per_m=None, avg_power=None, np=None,
                   rpe=6, source_name=None)
    fam, method, _tr, tss, _inp = compute_activity_load(li)
    assert fam == "strength"
    assert method == "rpetss"
    assert tss is not None and tss > 0
