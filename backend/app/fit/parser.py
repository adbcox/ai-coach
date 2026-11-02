"""Parse a Garmin activity download (ZIP containing one .fit file)."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import fitdecode

MAX_FIT_BYTES = 64 * 1024 * 1024
_SEMICIRCLE = 180.0 / 2**31


class FitError(Exception):
    pass


@dataclass
class Sample:
    t: int
    lat: float | None = None
    lon: float | None = None
    alt: float | None = None
    hr: int | None = None
    cadence: int | None = None
    power: int | None = None
    speed: float | None = None
    dist: float | None = None


@dataclass
class Lap:
    """One FIT lap message: what Garmin Connect shows as a split (automatic by distance, manual, or a workout step)."""
    index: int
    start_t: int | None = None
    elapsed_s: float | None = None
    timer_s: float | None = None
    distance_m: float | None = None
    avg_speed: float | None = None
    max_speed: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None
    ascent_m: float | None = None
    descent_m: float | None = None
    avg_cadence: float | None = None   # as stored in FIT: strides per minute for running (one foot)
    avg_power: float | None = None
    trigger: str | None = None
    intensity: str | None = None


def _lap_from_frame(frame: Any, index: int) -> Lap:
    start = _utc(_get(frame, "start_time"))
    dist = _num(_get(frame, "total_distance"))
    timer = _num(_get(frame, "total_timer_time"))
    speed = _num(_get(frame, "enhanced_avg_speed", "avg_speed"))
    if speed is None and dist and timer:
        speed = dist / timer
    trig, inten = _get(frame, "lap_trigger"), _get(frame, "intensity")
    return Lap(
        index=index, start_t=int(start.timestamp()) if start else None,
        elapsed_s=_num(_get(frame, "total_elapsed_time")), timer_s=timer, distance_m=dist, avg_speed=speed,
        max_speed=_num(_get(frame, "enhanced_max_speed", "max_speed")),
        avg_hr=_num(_get(frame, "avg_heart_rate")), max_hr=_num(_get(frame, "max_heart_rate")),
        ascent_m=_num(_get(frame, "total_ascent")), descent_m=_num(_get(frame, "total_descent")),
        avg_cadence=_num(_get(frame, "avg_cadence")), avg_power=_num(_get(frame, "avg_power")),
        trigger=str(trig) if trig is not None else None, intensity=str(inten) if inten is not None else None)


def parse_laps(data: bytes) -> list[Lap]:
    """Only the lap messages of a FIT file (used to backfill activities that were stored before laps were kept)."""
    laps: list[Lap] = []
    try:
        with fitdecode.FitReader(io.BytesIO(data)) as reader:
            for frame in reader:
                if isinstance(frame, fitdecode.FitDataMessage) and frame.name == "lap":
                    laps.append(_lap_from_frame(frame, len(laps)))
    except (fitdecode.FitError, EOFError, ValueError) as exc:
        raise FitError(f"Could not parse FIT file: {exc}") from exc
    return laps


@dataclass
class ParsedActivity:
    sport: str | None = None
    start_time: datetime | None = None
    distance_m: float | None = None
    duration_s: float | None = None
    elevation_gain_m: float | None = None
    avg_hr: float | None = None
    max_hr: float | None = None
    samples: list[Sample] = field(default_factory=list)
    laps: list[Lap] = field(default_factory=list)


def extract_fit(zip_bytes: bytes) -> bytes:
    """Safely pull the single .fit out of the download ZIP (size-capped)."""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            fits = [i for i in zf.infolist() if i.filename.lower().endswith(".fit")]
            if len(fits) != 1:
                raise FitError(f"Expected one .fit file in the download, found {len(fits)}.")
            info = fits[0]
            if info.file_size > MAX_FIT_BYTES:
                raise FitError("FIT file too large.")
            with zf.open(info) as handle:
                data = handle.read(MAX_FIT_BYTES + 1)
            if len(data) > MAX_FIT_BYTES:
                raise FitError("FIT file too large.")
            return data
    except zipfile.BadZipFile as exc:
        raise FitError("Download was not a valid ZIP file.") from exc


def _utc(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _get(frame: Any, *names: str) -> Any:
    for name in names:
        try:
            value = frame.get_value(name, fallback=None)
        except (KeyError, ValueError):
            value = None
        if value is not None:
            return value
    return None


def _degrees(value: Any) -> float | None:
    if value is None:
        return None
    value = float(value)
    return value if abs(value) <= 180 else value * _SEMICIRCLE


def _num(value: Any, cast: type = float) -> Any:
    try:
        return None if value is None else cast(value)
    except (TypeError, ValueError):
        return None


def parse_fit(data: bytes) -> ParsedActivity:
    out = ParsedActivity()
    session: dict[str, Any] = {}
    try:
        with fitdecode.FitReader(io.BytesIO(data)) as reader:
            for frame in reader:
                if not isinstance(frame, fitdecode.FitDataMessage):
                    continue
                if frame.name == "record":
                    ts = _utc(_get(frame, "timestamp"))
                    if ts is None:
                        continue
                    out.samples.append(Sample(
                        t=int(ts.timestamp()),
                        lat=_degrees(_get(frame, "position_lat")),
                        lon=_degrees(_get(frame, "position_long")),
                        alt=_num(_get(frame, "enhanced_altitude", "altitude")),
                        hr=_num(_get(frame, "heart_rate"), int),
                        cadence=_num(_get(frame, "cadence"), int),
                        power=_num(_get(frame, "power"), int),
                        speed=_num(_get(frame, "enhanced_speed", "speed")),
                        dist=_num(_get(frame, "distance")),
                    ))
                elif frame.name == "lap":
                    out.laps.append(_lap_from_frame(frame, len(out.laps)))
                elif frame.name == "session" and not session:
                    for key in ("sport", "start_time", "total_distance", "total_timer_time",
                                "total_elapsed_time", "total_ascent", "avg_heart_rate",
                                "max_heart_rate"):
                        session[key] = _get(frame, key)
    except (fitdecode.FitError, EOFError, ValueError) as exc:
        raise FitError(f"Could not parse FIT file: {exc}") from exc

    # de-duplicate on timestamp (primary key), keep first
    seen: set[int] = set()
    out.samples = [s for s in out.samples if not (s.t in seen or seen.add(s.t))]

    out.sport = str(session["sport"]) if session.get("sport") is not None else None
    out.start_time = _utc(session.get("start_time"))
    if out.start_time is None and out.samples:
        out.start_time = datetime.fromtimestamp(out.samples[0].t, tz=UTC)
    out.distance_m = _num(session.get("total_distance"))
    out.duration_s = _num(session.get("total_timer_time") or session.get("total_elapsed_time"))
    out.elevation_gain_m = _num(session.get("total_ascent"))
    out.avg_hr = _num(session.get("avg_heart_rate"))
    out.max_hr = _num(session.get("max_heart_rate"))
    if out.distance_m is None:
        dists = [s.dist for s in out.samples if s.dist is not None]
        out.distance_m = max(dists) if dists else None
    if out.duration_s is None and len(out.samples) > 1:
        out.duration_s = float(out.samples[-1].t - out.samples[0].t)
    return out
