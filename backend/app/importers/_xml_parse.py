"""Minimal GPX and TCX parsers for bulk-exported activities.

These produce the same `ParsedActivity` shape as `fit.parser`, so downstream
code (insert_activity, sample inserts) does not need to know the format.

Scope: GPX 1.1 track points with optional TrackPointExtension (hr/cad/power),
and TCX 2.0 Activities/Activity/Lap/Track/Trackpoint. Enough for every
Strava bulk export on record.
"""

from __future__ import annotations

from datetime import UTC, datetime
from math import cos, radians, sin, sqrt
from typing import Any
from xml.etree import ElementTree as ET  # noqa: S405 - XML is user-local, not untrusted RPC

from ..fit.parser import Lap, ParsedActivity, Sample

_GPX_NS = {
    "gpx": "http://www.topografix.com/GPX/1/1",
    "ext": "http://www.garmin.com/xmlschemas/TrackPointExtension/v1",
    "ext2": "http://www.garmin.com/xmlschemas/TrackPointExtension/v2",
}
_TCX_NS = {
    "tcx": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2",
    "ax": "http://www.garmin.com/xmlschemas/ActivityExtension/v2",
}


def _parse_iso(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        # Both GPX and TCX use UTC with a trailing Z.
        if text.endswith("Z"):
            return datetime.fromisoformat(text[:-1]).replace(tzinfo=UTC)
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _to_float(text: str | None) -> float | None:
    if text is None:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _to_int(text: str | None) -> int | None:
    val = _to_float(text)
    return int(val) if val is not None else None


def _haversine_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = radians(a[0]), radians(a[1])
    lat2, lon2 = radians(b[0]), radians(b[1])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    h = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6_371_000.0 * 2 * (h ** 0.5)  # equivalent to atan2 for small distances


def _accumulate_distance(points: list[tuple[float, float] | None], total_so_far: list[float]) -> None:
    for i, cur in enumerate(points):
        if i == 0 or cur is None or points[i - 1] is None:
            total_so_far.append(total_so_far[-1] if total_so_far else 0.0)
            continue
        inc = _haversine_m(points[i - 1], cur)  # type: ignore[arg-type]
        total_so_far.append(total_so_far[-1] + inc)


def parse_gpx(data: bytes) -> ParsedActivity:
    out = ParsedActivity()
    root = ET.fromstring(data)  # noqa: S314 - stdlib ET is fine for local files
    # GPX may have no namespace if the file is hand-edited; strip any ns prefix for findall.
    for trkpt in root.iter():
        tag = trkpt.tag.rsplit("}", 1)[-1]
        if tag != "trkpt":
            continue
        lat = _to_float(trkpt.attrib.get("lat"))
        lon = _to_float(trkpt.attrib.get("lon"))
        time_el = next((c for c in trkpt if c.tag.rsplit("}", 1)[-1] == "time"), None)
        ele_el = next((c for c in trkpt if c.tag.rsplit("}", 1)[-1] == "ele"), None)
        ts = _parse_iso(time_el.text if time_el is not None else None)
        if ts is None:
            continue
        hr = cad = power = None
        for ext in trkpt:
            if ext.tag.rsplit("}", 1)[-1] != "extensions":
                continue
            for node in ext.iter():
                tag_name = node.tag.rsplit("}", 1)[-1].lower()
                if tag_name == "hr":
                    hr = _to_int(node.text)
                elif tag_name in {"cad", "cadence"}:
                    cad = _to_int(node.text)
                elif tag_name in {"watts", "power"}:
                    power = _to_int(node.text)
        out.samples.append(Sample(
            t=int(ts.timestamp()),
            lat=lat, lon=lon,
            alt=_to_float(ele_el.text if ele_el is not None else None),
            hr=hr, cadence=cad, power=power,
        ))
    # Fill cumulative distance from GPS so downstream maths still works.
    if out.samples:
        cumulative: list[float] = []
        _accumulate_distance(
            [(s.lat, s.lon) if s.lat is not None and s.lon is not None else None for s in out.samples],
            cumulative,
        )
        for s, d in zip(out.samples, cumulative, strict=False):
            s.dist = d
        out.start_time = datetime.fromtimestamp(out.samples[0].t, tz=UTC)
        out.distance_m = cumulative[-1] if cumulative else None
        out.duration_s = float(out.samples[-1].t - out.samples[0].t)
        hrs = [s.hr for s in out.samples if s.hr is not None]
        out.avg_hr = sum(hrs) / len(hrs) if hrs else None
        out.max_hr = float(max(hrs)) if hrs else None
    # GPX has no sport field; leave as None and let dispatch route to 'other'.
    return out


def parse_tcx(data: bytes) -> ParsedActivity:
    out = ParsedActivity()
    root = ET.fromstring(data)  # noqa: S314
    # Find the first <Activity> element regardless of namespace prefix.
    activity_el: Any = None
    for el in root.iter():
        if el.tag.rsplit("}", 1)[-1] == "Activity":
            activity_el = el
            break
    if activity_el is None:
        return out
    sport = activity_el.attrib.get("Sport")
    out.sport = sport.lower() if sport else None
    laps: list[Lap] = []
    for lap_el in activity_el:
        if lap_el.tag.rsplit("}", 1)[-1] != "Lap":
            continue
        start_text = lap_el.attrib.get("StartTime")
        start_ts = _parse_iso(start_text)
        elapsed = distance = avg_hr = max_hr = None
        for field in lap_el:
            name = field.tag.rsplit("}", 1)[-1]
            if name == "TotalTimeSeconds":
                elapsed = _to_float(field.text)
            elif name == "DistanceMeters":
                distance = _to_float(field.text)
            elif name == "AverageHeartRateBpm":
                v = next((c for c in field if c.tag.rsplit("}", 1)[-1] == "Value"), None)
                avg_hr = _to_float(v.text) if v is not None else None
            elif name == "MaximumHeartRateBpm":
                v = next((c for c in field if c.tag.rsplit("}", 1)[-1] == "Value"), None)
                max_hr = _to_float(v.text) if v is not None else None
            elif name == "Track":
                for tpt in field:
                    if tpt.tag.rsplit("}", 1)[-1] != "Trackpoint":
                        continue
                    _read_trackpoint(tpt, out.samples)
        laps.append(Lap(
            index=len(laps),
            start_t=int(start_ts.timestamp()) if start_ts else None,
            elapsed_s=elapsed,
            timer_s=elapsed,
            distance_m=distance,
            avg_hr=avg_hr,
            max_hr=max_hr,
        ))
    out.laps = laps
    if out.samples:
        out.start_time = datetime.fromtimestamp(out.samples[0].t, tz=UTC)
        out.duration_s = float(out.samples[-1].t - out.samples[0].t)
        dists = [s.dist for s in out.samples if s.dist is not None]
        out.distance_m = max(dists) if dists else None
        hrs = [s.hr for s in out.samples if s.hr is not None]
        out.avg_hr = sum(hrs) / len(hrs) if hrs else None
        out.max_hr = float(max(hrs)) if hrs else None
    return out


def _read_trackpoint(tpt: Any, out_samples: list[Sample]) -> None:
    ts = lat = lon = alt = dist = speed = None
    hr: int | None = None
    cad: int | None = None
    power: int | None = None
    for c in tpt:
        name = c.tag.rsplit("}", 1)[-1]
        if name == "Time":
            ts = _parse_iso(c.text)
        elif name == "Position":
            for pc in c:
                pname = pc.tag.rsplit("}", 1)[-1]
                if pname == "LatitudeDegrees":
                    lat = _to_float(pc.text)
                elif pname == "LongitudeDegrees":
                    lon = _to_float(pc.text)
        elif name == "AltitudeMeters":
            alt = _to_float(c.text)
        elif name == "DistanceMeters":
            dist = _to_float(c.text)
        elif name == "HeartRateBpm":
            v = next((n for n in c if n.tag.rsplit("}", 1)[-1] == "Value"), None)
            hr = _to_int(v.text) if v is not None else None
        elif name == "Cadence":
            cad = _to_int(c.text)
        elif name == "Extensions":
            for ext in c.iter():
                ename = ext.tag.rsplit("}", 1)[-1]
                if ename == "Watts":
                    power = _to_int(ext.text)
                elif ename == "Speed":
                    speed = _to_float(ext.text)
    if ts is None:
        return
    out_samples.append(Sample(
        t=int(ts.timestamp()), lat=lat, lon=lon, alt=alt,
        hr=hr, cadence=cad, power=power, speed=speed, dist=dist,
    ))
