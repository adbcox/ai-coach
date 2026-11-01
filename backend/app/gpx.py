"""GPX 1.1 export for a recorded activity."""

from __future__ import annotations

from datetime import UTC, datetime
from xml.sax.saxutils import escape


def build_gpx(name: str, points) -> str:
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<gpx version="1.1" creator="ai-endurance-coach" '
        'xmlns="http://www.topografix.com/GPX/1/1" '
        'xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v1">',
        f"<trk><name>{escape(name)}</name><trkseg>",
    ]
    for p in points:
        when = datetime.fromtimestamp(p["t"], tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        ele = f"<ele>{p['alt']:.1f}</ele>" if p["alt"] is not None else ""
        ext = ""
        if p["hr"] is not None or p["cadence"] is not None:
            hr = f"<gpxtpx:hr>{int(p['hr'])}</gpxtpx:hr>" if p["hr"] is not None else ""
            cad = f"<gpxtpx:cad>{int(p['cadence'])}</gpxtpx:cad>" if p["cadence"] is not None else ""
            ext = f"<extensions><gpxtpx:TrackPointExtension>{hr}{cad}</gpxtpx:TrackPointExtension></extensions>"
        out.append(f'<trkpt lat="{p["lat"]:.6f}" lon="{p["lon"]:.6f}">{ele}<time>{when}</time>{ext}</trkpt>')
    out.append("</trkseg></trk></gpx>")
    return "\n".join(out)
