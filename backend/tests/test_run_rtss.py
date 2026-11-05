"""Run load — rTSS from pace vs threshold pace; hrTSS fallback."""

from app.coach_maths.load import LoadInput, compute_activity_load, rtss


def test_one_hour_at_threshold_pace_is_100_tss():
    # 4:10 /km = 250 s/km = 0.25 s/m
    # 14.4 km in 3600s at 250 s/km
    tss, inp = rtss(duration_s=3600, threshold_pace_s_per_m=0.25,
                    distance_m=14400, avg_hr=None)
    assert tss is not None
    assert 99.9 < tss < 100.1
    assert abs(inp["if_"] - 1.0) < 1e-6


def test_slower_than_threshold_gives_less_tss():
    # Same hour but ~4:38 /km (278 s/km) → below threshold
    tss, _ = rtss(3600, 0.25, 12960, None)
    assert tss is not None and 75 < tss < 85


def test_dispatch_run_trail_family():
    li = LoadInput(activity_id=1, sport_key="trail_running", duration_s=3600, distance_m=10000,
                   avg_hr=160, max_hr_user=190, ftp=None, lthr=160,
                   threshold_pace_s_per_m=0.3, css_s_per_m=None, avg_power=None, np=None,
                   rpe=None, source_name=None)
    fam, method, _tr, _tss, _inp = compute_activity_load(li)
    assert fam == "run_trail"
    assert method == "rtss"
