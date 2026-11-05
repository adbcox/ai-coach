"""Aerobic efficiency factor (Friel 2012).

* Bike: EF = NP (W) / avg_HR (bpm)
* Run:  EF = NGP (m/s) × 1000 / avg_HR  (expressed as m per 1000 heart-beats-equivalent)

Both return None if inputs are missing or the HR is implausibly low.
"""

from __future__ import annotations


def ef_bike(np: float | None, avg_hr: float | None) -> float | None:
    if not np or not avg_hr or avg_hr < 40 or np <= 0:
        return None
    return np / avg_hr


def ef_run(ngp_m_s: float | None, avg_hr: float | None) -> float | None:
    """Running EF. `ngp_m_s` is normalised graded pace as m/s (higher = faster)."""
    if not ngp_m_s or not avg_hr or avg_hr < 40 or ngp_m_s <= 0:
        return None
    # Use m/s * 60 / HR → metres per heart-beat-minute (1.5 is a healthy rec run).
    return (ngp_m_s * 60.0) / avg_hr
