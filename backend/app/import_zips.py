"""Offline activity importer.

Rebuilds the `activities`, `samples`, and `laps` rows from already-downloaded
Garmin .zip files on disk. No network, no Garmin client, no token read — this
is a recovery tool for the case where the SQLite file is damaged but the
activity blobs are intact.

Usage:
    python -m app.import_zips --data-dir /data

    # Optional overrides for scripted recovery:
    python -m app.import_zips --data-dir /data \
        --activities-dir /data/activities/garmin \
        --source garmin
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import db, laps as laps_module
from .fit.parser import FitError, ParsedActivity, extract_fit, parse_fit


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _insert(
    conn: sqlite3.Connection,
    source: str,
    source_id: str,
    parsed: ParsedActivity,
    rel_path: str,
) -> bool:
    """Mirror of app.sync._insert, but the summary blob is synthesised from
    the parsed FIT since we no longer have the original Garmin search payload."""
    if not parsed.start_time:
        return False
    summary = {
        "activityId": source_id,
        "startTimeGMT": parsed.start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "activityType": {"typeKey": parsed.sport} if parsed.sport else None,
        "distance": parsed.distance_m,
        "duration": parsed.duration_s,
        "elevationGain": parsed.elevation_gain_m,
        "averageHR": parsed.avg_hr,
        "maxHR": parsed.max_hr,
        "_source": "offline-import",
    }
    cur = conn.execute(
        "INSERT OR IGNORE INTO activities (source, source_id, start_time, sport, name, "
        "distance_m, duration_s, elevation_gain_m, avg_hr, max_hr, summary_json, file_path, "
        "has_samples, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            source, source_id, parsed.start_time.isoformat(), parsed.sport, None,
            parsed.distance_m, parsed.duration_s, parsed.elevation_gain_m,
            parsed.avg_hr, parsed.max_hr,
            json.dumps(summary), rel_path, 1 if parsed.samples else 0, _now(),
        ),
    )
    if cur.rowcount == 0:
        return False
    activity_id = cur.lastrowid
    conn.executemany(
        "INSERT OR IGNORE INTO samples (activity_id, t, lat, lon, alt, hr, cadence, power, "
        "speed, dist) VALUES (?,?,?,?,?,?,?,?,?,?)",
        [(activity_id, s.t, s.lat, s.lon, s.alt, s.hr, s.cadence, s.power, s.speed, s.dist)
         for s in parsed.samples],
    )
    laps_module.save_laps(conn, activity_id, parsed.laps)
    return True


def run(data_dir: Path, activities_dir: Path | None, source: str) -> int:
    activities_dir = activities_dir or (data_dir / "activities" / source)
    if not activities_dir.is_dir():
        print(f"ERROR: activities dir does not exist: {activities_dir}", file=sys.stderr)
        return 2
    db.init_db(data_dir / "db" / "coach.sqlite3")
    conn = db.connect(data_dir / "db" / "coach.sqlite3")
    try:
        inserted = skipped = failed = 0
        for zip_path in sorted(activities_dir.glob("*.zip")):
            source_id = zip_path.stem
            if not source_id.isdecimal():
                failed += 1
                print(f"skip (non-numeric id): {zip_path.name}", file=sys.stderr)
                continue
            try:
                parsed = parse_fit(extract_fit(zip_path.read_bytes()))
            except FitError as exc:
                failed += 1
                print(f"skip {source_id}: {exc}", file=sys.stderr)
                continue
            rel = f"activities/{source}/{source_id}.zip"
            if _insert(conn, source, source_id, parsed, rel):
                inserted += 1
            else:
                skipped += 1
            conn.commit()
            if (inserted + skipped + failed) % 25 == 0:
                print(f"progress: inserted={inserted} skipped={skipped} failed={failed}")
        print(f"done: inserted={inserted} skipped={skipped} failed={failed}")
        return 0 if failed == 0 else 1
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline reindex of stored .zip activities.")
    parser.add_argument("--data-dir", type=Path, required=True,
                        help="App data dir (holds db/ and activities/).")
    parser.add_argument("--activities-dir", type=Path, default=None,
                        help="Override: directory of .zip files to index.")
    parser.add_argument("--source", default="garmin",
                        help="Source tag to store on each row (default: garmin).")
    args = parser.parse_args(argv)
    return run(args.data_dir, args.activities_dir, args.source)


if __name__ == "__main__":
    raise SystemExit(main())
