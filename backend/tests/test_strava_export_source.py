"""Check that sport keys we pull from activity rows map to known families.

Strava and Garmin both export a sport-ish string. We don't want a Strava-sourced
row to end up in family 'other' when it should obviously be running or cycling.
Covers the full sport key → family table.
"""

from app.coach_maths.sport import FAMILIES, family_for, methods_for


def test_known_keys_hit_expected_families():
    cases = {
        "running": "run_road",
        "treadmill_running": "run_road",
        "trail_running": "run_trail",
        "ultra_running": "run_trail",
        "cycling": "bike_road",
        "road_biking": "bike_road",
        "indoor_cycling": "bike_indoor",
        "mountain_biking": "bike_trail",
        "gravel_cycling": "bike_trail",
        "lap_swimming": "swim_pool",
        "open_water_swimming": "swim_open",
        "strength_training": "strength",
    }
    for key, fam in cases.items():
        assert family_for(key) == fam, key


def test_unknown_or_empty_goes_to_other():
    assert family_for(None) == "other"
    assert family_for("") == "other"
    assert family_for("underwater_hockey") == "other"


def test_every_family_has_methods():
    for fam in FAMILIES:
        primary, _ = methods_for(fam)
        assert primary in {"power_tss", "hrtss", "rtss", "stss", "rpetss", "duration"}
