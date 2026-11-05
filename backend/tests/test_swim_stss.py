"""Swim sTSS — (swim_speed/CSS)^3 × duration_h × 100."""

from app.coach_maths.load import LoadInput, compute_activity_load, stss


def test_one_hour_at_css_is_100_tss():
    # CSS 1:36 /100m ≈ 0.96 s/m. In 3600 s covers ~3750 m.
    tss, _ = stss(duration_s=3600, css_s_per_m=0.96, distance_m=3600 / 0.96)
    assert tss is not None
    assert 99.9 < tss < 100.1


def test_half_css_pace_cubes_tss():
    # pool_swimming slower than CSS → tss < 100
    tss, _ = stss(duration_s=3600, css_s_per_m=0.96, distance_m=3000)
    assert tss is not None and tss < 100


def test_dispatch_swim_pool_family():
    li = LoadInput(activity_id=1, sport_key="lap_swimming", duration_s=1800, distance_m=1500,
                   avg_hr=140, max_hr_user=190, ftp=None, lthr=160,
                   threshold_pace_s_per_m=None, css_s_per_m=0.96, avg_power=None, np=None,
                   rpe=None, source_name=None)
    fam, method, _tr, _tss, _inp = compute_activity_load(li)
    assert fam == "swim_pool"
    assert method == "stss"
