"""Climb detection — from distance + altitude samples."""

from app.coach_maths.ride_analysis import detect_climbs


def test_flat_route_detects_no_climbs():
    dist = [float(i) * 10.0 for i in range(1000)]     # 10 km @ 10 m/s
    alt = [100.0] * 1000
    assert detect_climbs(dist, alt) == []


def test_steady_6pct_climb_is_detected():
    # 2 km stretch with 6% average gradient, dense samples
    dist = [i * 10.0 for i in range(201)]             # 0 to 2000 m
    alt = [100.0 + i * 0.6 for i in range(201)]       # rises 120 m total
    climbs = detect_climbs(dist, alt, min_length_m=500, min_gradient_pct=3)
    assert len(climbs) == 1
    c = climbs[0]
    assert c["length_m"] >= 1999
    assert 5.5 < c["avg_gradient"] < 6.5


def test_below_threshold_grade_filtered():
    dist = [i * 10.0 for i in range(201)]
    alt = [100.0 + i * 0.1 for i in range(201)]       # 1% grade
    climbs = detect_climbs(dist, alt, min_length_m=500, min_gradient_pct=3)
    assert climbs == []
