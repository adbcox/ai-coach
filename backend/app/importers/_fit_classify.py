"""Read a FIT file's `file_id` message to work out which app wrote it.

Zwift writes `manufacturer=zwift` (numeric 260) in `file_id`; Strava's
desktop Zwift uploads keep this intact. Everything else is classified as
'strava_export' (the file came from a Strava bulk export, but we don't know
which app originally produced it — Wahoo, Suunto, TrainerRoad, etc.).
"""

from __future__ import annotations

import io
from typing import Any

import fitdecode


def classify_fit(data: bytes) -> str:
    """Return 'zwift_export' or 'strava_export'."""
    try:
        with fitdecode.FitReader(io.BytesIO(data)) as reader:
            for frame in reader:
                if not isinstance(frame, fitdecode.FitDataMessage):
                    continue
                if frame.name != "file_id":
                    continue
                mfg = _field(frame, "manufacturer")
                if mfg is None:
                    return "strava_export"
                if isinstance(mfg, str) and mfg.lower() == "zwift":
                    return "zwift_export"
                if isinstance(mfg, int) and mfg == 260:
                    return "zwift_export"
                return "strava_export"
    except (fitdecode.FitError, EOFError, ValueError):
        return "strava_export"
    return "strava_export"


def _field(frame: Any, name: str) -> Any:
    try:
        return frame.get_value(name)
    except KeyError:
        return None
