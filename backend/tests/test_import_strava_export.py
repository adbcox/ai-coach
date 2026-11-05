"""Strava bulk-export importer, exercised via a synthetic .gpx and .tcx file.

Those two formats are stdlib-friendly (XML), so we can build them on the
fly without a real recorded ride. The FIT branch is covered separately
by `_fit_classify` when real FIT bytes are available; the dedup rule is
covered by test_import_dedup.
"""

from __future__ import annotations

import io
import zipfile

from app import db
from app.config import Settings
from app.importers import strava_export


_GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="unit-test" xmlns="http://www.topografix.com/GPX/1/1">
<trk><trkseg>
  <trkpt lat="38.900" lon="-77.030"><ele>50</ele><time>2026-10-10T10:00:00Z</time></trkpt>
  <trkpt lat="38.901" lon="-77.030"><ele>51</ele><time>2026-10-10T10:00:10Z</time></trkpt>
  <trkpt lat="38.902" lon="-77.030"><ele>52</ele><time>2026-10-10T10:00:20Z</time></trkpt>
</trkseg></trk></gpx>"""


_TCX = """<?xml version="1.0" encoding="UTF-8"?>
<TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">
<Activities><Activity Sport="Running">
  <Lap StartTime="2026-10-11T08:00:00Z">
    <TotalTimeSeconds>60</TotalTimeSeconds>
    <DistanceMeters>200</DistanceMeters>
    <Track>
      <Trackpoint><Time>2026-10-11T08:00:00Z</Time>
        <Position><LatitudeDegrees>38.9</LatitudeDegrees><LongitudeDegrees>-77.0</LongitudeDegrees></Position>
        <DistanceMeters>0</DistanceMeters>
        <HeartRateBpm><Value>120</Value></HeartRateBpm></Trackpoint>
      <Trackpoint><Time>2026-10-11T08:00:30Z</Time>
        <Position><LatitudeDegrees>38.9005</LatitudeDegrees><LongitudeDegrees>-77.0</LongitudeDegrees></Position>
        <DistanceMeters>100</DistanceMeters>
        <HeartRateBpm><Value>140</Value></HeartRateBpm></Trackpoint>
      <Trackpoint><Time>2026-10-11T08:01:00Z</Time>
        <Position><LatitudeDegrees>38.901</LatitudeDegrees><LongitudeDegrees>-77.0</LongitudeDegrees></Position>
        <DistanceMeters>200</DistanceMeters>
        <HeartRateBpm><Value>150</Value></HeartRateBpm></Trackpoint>
    </Track>
  </Lap>
</Activity></Activities></TrainingCenterDatabase>"""


def _make_zip(tmp_path):
    archive = tmp_path / "strava_export.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("activities.csv",
                    "Filename,Activity Name\nactivities/a.gpx,GPX ride\nactivities/b.tcx,TCX run\n")
        zf.writestr("activities/a.gpx", _GPX)
        zf.writestr("activities/b.tcx", _TCX)
    archive.write_bytes(buf.getvalue())
    return archive


def test_imports_gpx_and_tcx(tmp_path):
    settings = Settings(data_dir=tmp_path, request_delay_s=0)
    archive = _make_zip(tmp_path)
    stats = strava_export.run(archive, tmp_path, commit_every=10)
    assert stats.activities_inserted == 2
    assert stats.strava_inserted == 2
    assert stats.zwift_inserted == 0
    conn = db.connect(settings.db_path)
    rows = conn.execute(
        "SELECT source, sport, name FROM activities ORDER BY start_time"
    ).fetchall()
    srcs = [r["source"] for r in rows]
    assert srcs == ["strava_export", "strava_export"]
    # GPX has no sport, TCX had Sport='Running' → lowercased.
    assert rows[1]["sport"] == "running"
    assert rows[0]["name"] == "GPX ride"


def test_rerun_is_idempotent(tmp_path):
    archive = _make_zip(tmp_path)
    stats1 = strava_export.run(archive, tmp_path)
    stats2 = strava_export.run(archive, tmp_path)
    assert stats1.activities_inserted == 2
    assert stats2.activities_inserted == 0
    assert stats2.activities_skipped_already == 2


def test_dedup_against_prior_source(tmp_path):
    """A pre-existing garmin row should block the same ride from being
    inserted again by the Strava export importer."""
    settings = Settings(data_dir=tmp_path, request_delay_s=0)
    db.init_db(settings.db_path)
    conn = db.connect(settings.db_path)
    # Pre-seed a near-identical ride from the GPX (~222 m of travel, 20 s).
    conn.execute(
        "INSERT INTO activities (source, source_id, start_time, sport, name, "
        "distance_m, duration_s, created_at) "
        "VALUES ('garmin', '1', '2026-10-10T10:00:00+00:00', 'cycling', 'x', "
        "        222.0, 20.0, '2026-11-05T00:00:00+00:00')",
    )
    conn.commit()
    conn.close()
    archive = _make_zip(tmp_path)
    stats = strava_export.run(archive, tmp_path)
    # GPX is a near-dup → should be skipped. TCX (different day) still imports.
    assert stats.activities_skipped_dupe == 1
    assert stats.activities_inserted == 1
