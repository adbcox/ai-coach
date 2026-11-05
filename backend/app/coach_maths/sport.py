"""Sport key → family mapping, with default load methods per family.

Garmin's activity typeKey is a free-ish string ("running", "trail_running",
"cycling", "mountain_biking", "indoor_cycling", "lap_swimming", "open_water_swimming",
"strength_training", "hiking", "walking", "other", ...). We collapse those
into a small set of families the maths dispatches on.
"""

from __future__ import annotations

from datetime import UTC, datetime

# All sport families. Keep this list short — every new family means new
# analysis code paths and new test fixtures.
FAMILIES = (
    "bike_road",
    "bike_indoor",
    "bike_trail",
    "run_road",
    "run_trail",
    "swim_pool",
    "swim_open",
    "strength",
    "other",
)

# Prefix-based mapping: Garmin keys tend to share a verb ("running" vs
# "trail_running"), so we match on specific-first substrings.
_RULES: list[tuple[str, str]] = [
    ("trail_running", "run_trail"),
    ("ultra_running", "run_trail"),
    ("mountain_running", "run_trail"),
    ("running", "run_road"),
    ("treadmill_running", "run_road"),
    ("indoor_running", "run_road"),
    ("track_running", "run_road"),
    ("obstacle_run", "run_trail"),
    ("mountain_biking", "bike_trail"),
    ("gravel_cycling", "bike_trail"),
    ("cyclocross", "bike_trail"),
    ("indoor_cycling", "bike_indoor"),
    ("virtual_ride", "bike_indoor"),
    ("cycling", "bike_road"),
    ("road_biking", "bike_road"),
    ("open_water_swimming", "swim_open"),
    ("lap_swimming", "swim_pool"),
    ("pool_swimming", "swim_pool"),
    ("swimming", "swim_pool"),
    ("strength_training", "strength"),
    ("weight_training", "strength"),
]

# Default load methods per family. "primary" is tried first; if its inputs
# are missing the dispatcher falls back to "fallback".
_FAMILY_DEFAULTS: dict[str, tuple[str, str | None]] = {
    "bike_road":   ("power_tss", "hrtss"),
    "bike_indoor": ("power_tss", "hrtss"),
    "bike_trail":  ("hrtss", "duration"),
    "run_road":    ("rtss", "hrtss"),
    "run_trail":   ("rtss", "hrtss"),
    "swim_pool":   ("stss", "hrtss"),
    "swim_open":   ("stss", "hrtss"),
    "strength":    ("rpetss", "duration"),
    "other":       ("hrtss", "duration"),
}


def family_for(sport_key: str | None) -> str:
    """Return the family (e.g. 'run_road') for a Garmin typeKey. Unknown → 'other'."""
    if not sport_key:
        return "other"
    k = sport_key.strip().lower()
    for needle, family in _RULES:
        if needle in k:
            return family
    return "other"


def methods_for(family: str) -> tuple[str, str | None]:
    """(primary, fallback) load methods for a family. Unknown family → ('hrtss', 'duration')."""
    return _FAMILY_DEFAULTS.get(family, ("hrtss", "duration"))


def seed_sport(conn, sport_key: str | None) -> str:
    """Upsert a row in `sports` for `sport_key` and return its family."""
    family = family_for(sport_key)
    primary, fallback = methods_for(family)
    label = (sport_key or "other").replace("_", " ")
    conn.execute(
        "INSERT INTO sports (key, label, family, load_method_primary, "
        "load_method_fallback, zones_axes_json, created_at) VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET label=excluded.label, family=excluded.family, "
        "load_method_primary=excluded.load_method_primary, "
        "load_method_fallback=excluded.load_method_fallback",
        (sport_key or "other", label, family, primary, fallback, None,
         datetime.now(UTC).isoformat(timespec="seconds")),
    )
    return family
