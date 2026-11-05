"""Bike load — power-TSS primary with hrTSS fallback (Coggan)."""

from app.coach_maths.load import LoadInput, compute_activity_load, power_tss


def test_one_hour_at_ftp_is_100_tss():
    tss, inp = power_tss(duration_s=3600, np=250.0, avg_power=240.0, ftp=250.0)
    assert tss is not None
    assert 99.9 < tss < 100.1
    assert inp["if_"] == 1.0


def test_halving_duration_halves_tss():
    full, _ = power_tss(3600, 250, 240, 250)
    half, _ = power_tss(1800, 250, 240, 250)
    assert full and half and abs(full - half * 2) < 0.1


def test_falls_back_to_hrtss_when_no_power():
    li = LoadInput(activity_id=1, sport_key="cycling", duration_s=3600, distance_m=30000,
                   avg_hr=150, max_hr_user=190, ftp=None, lthr=160,
                   threshold_pace_s_per_m=None, css_s_per_m=None, avg_power=None, np=None,
                   rpe=None, source_name=None)
    fam, method, _tr, tss, _inp = compute_activity_load(li)
    assert fam == "bike_road"
    assert method == "hrtss"
    assert tss is not None and tss > 0


def test_dispatch_assigns_bike_indoor_family():
    li = LoadInput(activity_id=1, sport_key="indoor_cycling", duration_s=3600, distance_m=0,
                   avg_hr=140, max_hr_user=190, ftp=250, lthr=160,
                   threshold_pace_s_per_m=None, css_s_per_m=None, avg_power=220, np=230,
                   rpe=None, source_name=None)
    fam, method, _tr, _tss, _inp = compute_activity_load(li)
    assert fam == "bike_indoor"
    assert method == "power_tss"
