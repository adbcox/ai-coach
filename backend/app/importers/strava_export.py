"""Strava "Download your data" bulk-export importer (D6).

No Strava API calls. The ZIP that Strava emails you contains an
`activities.csv` manifest and an `activities/` directory with one file per
upload in its original format (fit/gpx/tcx, sometimes gzipped). We parse
those originals; the CSV is only consulted for the activity name, which
FIT/GPX/TCX often lack.

Classification:
  - FIT file where `file_id.manufacturer == zwift` (260)   → source='zwift_export'
  - Everything else                                       → source='strava_export'

Dedup: ±60 s start_time + similar distance + similar duration against
existing activities (incl. Garmin-API rows and Garmin-export rows).

CLI:
    python -m app.importers.strava_export /path/to/strava_export.zip \\
        [--data-dir /data] [--commit-every 25]
"""

from __future__ import annotations

import argparse
import csv
import gzip
import io
import sqlite3
import sys
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .. import db
from ..config import Settings
from ..fit.parser import FitError, ParsedActivity, parse_fit
from ._common import (
    CandidateRow,
    find_duplicate,
    insert_activity,
    mark_canonical_link,
    now_iso,
    save_bytes,
    sha256_of,
)
from ._fit_classify import classify_fit
from ._xml_parse import parse_gpx, parse_tcx


@dataclass
class ImportStats:
    activities_inserted: int = 0
    zwift_inserted: int = 0
    strava_inserted: int = 0
    activities_skipped_dupe: int = 0
    activities_skipped_already: int = 0
    activities_failed: int = 0


def _read_manifest(zf: zipfile.ZipFile) -> dict[str, str]:
    """Map `activities/<file>` → activity name (as shown on Strava)."""
    for info in zf.infolist():
        if Path(info.filename).name.lower() == "activities.csv":
            with zf.open(info) as fh:
                text = fh.read().decode("utf-8-sig", errors="replace")
            rdr = csv.DictReader(io.StringIO(text))
            out: dict[str, str] = {}
            for row in rdr:
                fname = (row.get("Filename") or row.get("filename") or "").strip()
                name = (row.get("Activity Name") or row.get("activity_name") or "").strip()
                if fname and name:
                    out[fname] = name
            return out
    return {}


def _decompress(data: bytes, filename: str) -> bytes:
    if filename.lower().endswith(".gz"):
        try:
            return gzip.decompress(data)
        except (OSError, EOFError):
            raise FitError("bad gzip")  # re-use the typed exception
    return data


def _parse_any(data: bytes, filename: str) -> tuple[str, ParsedActivity | None]:
    """Return (source, parsed) where source is 'fit', 'gpx', 'tcx', or ''
    and parsed is None if it couldn't be parsed."""
    stem = filename.lower().rstrip(".gz")
    if stem.endswith(".fit"):
        try:
            return "fit", parse_fit(data)
        except FitError:
            return "fit", None
    if stem.endswith(".gpx"):
        try:
            return "gpx", parse_gpx(data)
        except Exception:  # noqa: BLE001 - defensive, any XML weirdness
            return "gpx", None
    if stem.endswith(".tcx"):
        try:
            return "tcx", parse_tcx(data)
        except Exception:  # noqa: BLE001 - defensive, any XML weirdness
            return "tcx", None
    return "", None


def _import_one(
    conn: sqlite3.Connection,
    data: bytes,
    rel_name: str,
    data_dir: Path,
    name_override: str | None,
    stats: ImportStats,
) -> None:
    try:
        raw = _decompress(data, rel_name)
    except FitError:
        stats.activities_failed += 1
        return
    ext, parsed = _parse_any(raw, rel_name)
    if parsed is None or parsed.start_time is None:
        stats.activities_failed += 1
        return
    digest = sha256_of(raw)
    if ext == "fit":
        source = classify_fit(raw)  # 'zwift_export' or 'strava_export'
    else:
        source = "strava_export"
    already = conn.execute(
        "SELECT id FROM activities WHERE source=? AND source_id=?",
        (source, digest),
    ).fetchone()
    if already:
        stats.activities_skipped_already += 1
        return
    cand = CandidateRow(
        start_time=parsed.start_time,
        distance_m=parsed.distance_m,
        duration_s=parsed.duration_s,
        sport=parsed.sport,
    )
    existing = find_duplicate(conn, cand)
    if existing is not None:
        mark_canonical_link(conn, existing)
        stats.activities_skipped_dupe += 1
        return
    out_path = data_dir / "activities" / source / f"{digest}.{ext}"
    save_bytes(raw, out_path)
    summary = {
        "startTimeGMT": parsed.start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "activityType": {"typeKey": parsed.sport} if parsed.sport else None,
        "distance": parsed.distance_m,
        "duration": parsed.duration_s,
        "elevationGain": parsed.elevation_gain_m,
        "averageHR": parsed.avg_hr,
        "maxHR": parsed.max_hr,
        "_source": source.replace("_export", "-export"),
        "_format": ext,
        "_orig_name": rel_name,
    }
    aid = insert_activity(
        conn,
        source=source,
        source_id=digest,
        start_time=parsed.start_time,
        sport=parsed.sport,
        name=name_override,
        distance_m=parsed.distance_m,
        duration_s=parsed.duration_s,
        elevation_gain_m=parsed.elevation_gain_m,
        avg_hr=parsed.avg_hr,
        max_hr=parsed.max_hr,
        file_path=f"activities/{source}/{digest}.{ext}",
        summary=summary,
        samples=parsed.samples,
        laps=parsed.laps,
    )
    if aid is None:
        stats.activities_skipped_already += 1
        return
    mark_canonical_link(conn, aid)
    stats.activities_inserted += 1
    if source == "zwift_export":
        stats.zwift_inserted += 1
    else:
        stats.strava_inserted += 1


def _walk_zip(zf: zipfile.ZipFile, conn: sqlite3.Connection, data_dir: Path,
              names: dict[str, str], stats: ImportStats, commit_every: int) -> None:
    count = 0
    for info in zf.infolist():
        if info.is_dir():
            continue
        rel = info.filename
        stem = rel.lower().rstrip(".gz")
        if not stem.endswith((".fit", ".gpx", ".tcx")):
            continue
        with zf.open(info) as fh:
            data = fh.read()
        _import_one(conn, data, rel, data_dir,
                    names.get(rel) or names.get(Path(rel).name), stats)
        count += 1
        if count % commit_every == 0:
            conn.commit()
            print(f"progress: {stats}")
    conn.commit()


def _walk_dir(root: Path, conn: sqlite3.Connection, data_dir: Path,
              stats: ImportStats, commit_every: int) -> None:
    count = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        stem = path.name.lower().rstrip(".gz")
        if not stem.endswith((".fit", ".gpx", ".tcx")):
            continue
        _import_one(conn, path.read_bytes(), str(path.relative_to(root)),
                    data_dir, None, stats)
        count += 1
        if count % commit_every == 0:
            conn.commit()
            print(f"progress: {stats}")
    conn.commit()


def run(archive_path: Path, data_dir: Path, commit_every: int = 25) -> ImportStats:
    stats = ImportStats()
    db.init_db(data_dir / "db" / "coach.sqlite3")
    conn = db.connect(data_dir / "db" / "coach.sqlite3")
    try:
        if archive_path.is_dir():
            _walk_dir(archive_path, conn, data_dir, stats, commit_every)
        elif zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path) as zf:
                names = _read_manifest(zf)
                _walk_zip(zf, conn, data_dir, names, stats, commit_every)
        else:
            raise SystemExit(f"Not a zip or directory: {archive_path}")
    finally:
        conn.close()
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Import a Strava bulk-data export.")
    ap.add_argument("archive", type=Path, help="Path to strava_export.zip or an extracted dir.")
    ap.add_argument("--data-dir", type=Path,
                    default=Path(Settings().data_dir),
                    help="App data dir (holds db/ and activities/).")
    ap.add_argument("--commit-every", type=int, default=25)
    args = ap.parse_args(argv)
    stats = run(args.archive, args.data_dir, args.commit_every)
    print(f"done: {stats}")
    return 0 if stats.activities_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
