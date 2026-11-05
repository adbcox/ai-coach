"""Garmin Connect "Account Export" importer (offline).

Takes the big ZIP (or an already-extracted directory) and inserts:
  - every .fit file as an `activities` row with source='garmin_export',
    source_id = hex sha-256 of the file contents.
  - every readable health CSV as `wellness_raw` rows with kind prefixed
    `export_` so the P2 readiness code can see them without being fooled
    into thinking they are API-shaped payloads.

No network calls, no GarminClient import. Dedup against existing
activities by ±60 s / distance / duration.

CLI:
    python -m app.importers.garmin_export \\
        /path/to/export.zip \\
        [--data-dir /data] [--commit-every 25]
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sqlite3
import sys
import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from .. import db
from ..config import Settings
from ..fit.parser import FitError, parse_fit
from ._common import (
    CandidateRow,
    find_duplicate,
    insert_activity,
    mark_canonical_link,
    now_iso,
    save_bytes,
    sha256_of,
)


@dataclass
class ImportStats:
    activities_inserted: int = 0
    activities_skipped_dupe: int = 0
    activities_skipped_already: int = 0
    activities_failed: int = 0
    wellness_rows: int = 0


def _looks_like_fit(name: str) -> bool:
    return name.lower().endswith(".fit")


_WELLNESS_KIND_MAP = (
    # (regex on filename, kind used in wellness_raw)
    (re.compile(r"sleep", re.I), "export_sleep"),
    (re.compile(r"hrv|heart[_-]?rate[_-]?variability", re.I), "export_hrv"),
    (re.compile(r"body[_-]?battery|stress", re.I), "export_stress"),
    (re.compile(r"resting[_-]?heart|rhr", re.I), "export_rhr"),
    (re.compile(r"steps", re.I), "export_steps"),
    (re.compile(r"weight", re.I), "export_weight"),
    (re.compile(r"respiration|spo2|pulse[_-]?ox", re.I), "export_respiration"),
    (re.compile(r"daily[_-]?summary|summary[_-]?daily", re.I), "export_daily_summaries"),
)


def _kind_for_csv(name: str) -> str | None:
    base = Path(name).name
    for rx, kind in _WELLNESS_KIND_MAP:
        if rx.search(base):
            return kind
    return None


def _import_fit(
    conn: sqlite3.Connection,
    data: bytes,
    rel_path: str,
    data_dir: Path,
    stats: ImportStats,
) -> None:
    try:
        parsed = parse_fit(data)
    except FitError:
        stats.activities_failed += 1
        return
    if parsed.start_time is None:
        stats.activities_failed += 1
        return
    digest = sha256_of(data)
    # Same-source dedup (same file imported twice): the (source, source_id) UNIQUE
    # constraint handles that; we just check so the stats reflect it.
    already = conn.execute(
        "SELECT id FROM activities WHERE source='garmin_export' AND source_id=?",
        (digest,),
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
    out_path = data_dir / "activities" / "garmin_export" / f"{digest}.fit"
    save_bytes(data, out_path)
    summary = {
        "startTimeGMT": parsed.start_time.strftime("%Y-%m-%d %H:%M:%S"),
        "activityType": {"typeKey": parsed.sport} if parsed.sport else None,
        "distance": parsed.distance_m,
        "duration": parsed.duration_s,
        "elevationGain": parsed.elevation_gain_m,
        "averageHR": parsed.avg_hr,
        "maxHR": parsed.max_hr,
        "_source": "garmin-export",
        "_orig_path": rel_path,
    }
    aid = insert_activity(
        conn,
        source="garmin_export",
        source_id=digest,
        start_time=parsed.start_time,
        sport=parsed.sport,
        name=None,
        distance_m=parsed.distance_m,
        duration_s=parsed.duration_s,
        elevation_gain_m=parsed.elevation_gain_m,
        avg_hr=parsed.avg_hr,
        max_hr=parsed.max_hr,
        file_path=f"activities/garmin_export/{digest}.fit",
        summary=summary,
        samples=parsed.samples,
        laps=parsed.laps,
    )
    if aid is None:
        stats.activities_skipped_already += 1
    else:
        mark_canonical_link(conn, aid)
        stats.activities_inserted += 1


def _import_csv(
    conn: sqlite3.Connection,
    data: bytes,
    name: str,
    stats: ImportStats,
) -> None:
    kind = _kind_for_csv(name)
    if kind is None:
        return
    try:
        text = data.decode("utf-8-sig", errors="replace")
    except Exception:  # noqa: BLE001 - defensive, any decode weirdness
        return
    rdr = csv.DictReader(io.StringIO(text))
    header = rdr.fieldnames or []
    date_col = None
    for col in header:
        if col.lower() in {"date", "day", "calendar_date", "calendardate"}:
            date_col = col
            break
    if date_col is None:
        # Some Garmin CSVs are timestamp-indexed, not date-indexed; bucket them
        # by UTC date of the ts column if we find one.
        for col in header:
            if "time" in col.lower() or "timestamp" in col.lower():
                date_col = col
                break
    if date_col is None:
        return
    buckets: dict[str, list[dict[str, str]]] = {}
    for row in rdr:
        raw = (row.get(date_col) or "").strip()
        if not raw:
            continue
        day = raw[:10]
        try:
            date.fromisoformat(day)
        except ValueError:
            continue
        buckets.setdefault(day, []).append(row)
    for day, rows in buckets.items():
        payload = json.dumps({"source": "garmin_export", "file": Path(name).name,
                              "rows": rows})
        conn.execute(
            "INSERT OR REPLACE INTO wellness_raw (source, kind, start_date, end_date, "
            "fetched_at, is_empty, payload) VALUES ('garmin_export', ?, ?, ?, ?, ?, ?)",
            (kind, day, day, now_iso(), 1 if not rows else 0, payload),
        )
        stats.wellness_rows += 1


def _walk_zip(zf: zipfile.ZipFile, conn: sqlite3.Connection, data_dir: Path,
              stats: ImportStats, commit_every: int) -> None:
    count = 0
    for info in zf.infolist():
        if info.is_dir():
            continue
        name = info.filename
        if _looks_like_fit(name):
            with zf.open(info) as fh:
                data = fh.read()
            _import_fit(conn, data, name, data_dir, stats)
        elif name.lower().endswith(".fit.gz"):
            # Account exports sometimes gzip individual fit files.
            import gzip
            with zf.open(info) as fh:
                try:
                    data = gzip.decompress(fh.read())
                except (OSError, EOFError):
                    stats.activities_failed += 1
                    continue
            _import_fit(conn, data, name, data_dir, stats)
        elif name.lower().endswith((".csv", ".json")):
            if name.lower().endswith(".csv"):
                with zf.open(info) as fh:
                    _import_csv(conn, fh.read(), name, stats)
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
        name = str(path.relative_to(root))
        if _looks_like_fit(name):
            _import_fit(conn, path.read_bytes(), name, data_dir, stats)
        elif name.lower().endswith(".csv"):
            _import_csv(conn, path.read_bytes(), name, stats)
        count += 1
        if count % commit_every == 0:
            conn.commit()
            print(f"progress: {stats}")
    conn.commit()


def run(archive_path: Path, data_dir: Path, commit_every: int = 25) -> ImportStats:
    """Entry point used by the CLI and tests."""
    stats = ImportStats()
    db.init_db(data_dir / "db" / "coach.sqlite3")
    conn = db.connect(data_dir / "db" / "coach.sqlite3")
    try:
        if archive_path.is_dir():
            _walk_dir(archive_path, conn, data_dir, stats, commit_every)
        elif zipfile.is_zipfile(archive_path):
            with zipfile.ZipFile(archive_path) as zf:
                _walk_zip(zf, conn, data_dir, stats, commit_every)
        else:
            raise SystemExit(f"Not a zip or directory: {archive_path}")
    finally:
        conn.close()
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Import a Garmin account export (ZIP or dir).")
    ap.add_argument("archive", type=Path, help="Path to export.zip or an extracted dir.")
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
