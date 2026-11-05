"""coach-maths — pure numerics for load, readiness, and per-activity analysis.

This package is unit-tested numbers only. It never makes network calls, never
asks an LLM anything, and never writes to tables outside the P2 set
(sports, activity_load, training_load_day, training_load_day_family,
readiness_day, checkins, ride_metrics, time_in_zone, climbs,
mean_max_power, mean_max_pace, swim_splits, detected_intervals,
vdot_state, vdot_events, thresholds_staleness).
"""

from __future__ import annotations

from . import efficiency, load, readiness, ride_analysis, sport, staleness, vdot_state

__all__ = [
    "efficiency",
    "load",
    "readiness",
    "ride_analysis",
    "sport",
    "staleness",
    "vdot_state",
]
