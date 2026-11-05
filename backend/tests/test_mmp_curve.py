"""Mean-max power curve — best rolling mean over each window."""

from app.coach_maths.ride_analysis import mean_max_curve, normalised_power, rolling_mean


def test_rolling_mean_shortens_until_window_full():
    out = rolling_mean([None] * 5 + [100.0] * 60, window_s=30, dt_s=1.0)
    # Early entries that are None → still None; later entries hit 100.
    assert out[0] is None
    assert out[-1] == 100


def test_mmp_captures_peak_window():
    series = [50.0] * 60 + [300.0] * 30 + [50.0] * 60   # 30s peak at 300
    curve = mean_max_curve(series, [15, 30, 60])
    assert 290 < curve[30] < 305
    # 60s window straddles the peak so it averages down
    assert curve[60] < 250


def test_normalised_power_rewards_variable_pace():
    steady = [200.0] * 3600
    surgy = [100.0 if i % 2 else 300.0 for i in range(3600)]
    np_steady = normalised_power(steady)
    np_surgy = normalised_power(surgy)
    assert np_steady is not None and np_surgy is not None
    # Steady at 200 → NP 200; surgy centred on 200 → NP > 200
    assert abs(np_steady - 200.0) < 1
    assert np_surgy > np_steady
