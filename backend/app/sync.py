"""Garmin -> SQLite sync."""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from . import db, schedule
from .config import Settings
from .crypto import SecretBox
from .fit.parser import FitError, ParsedActivity, extract_fit, parse_fit
from .garmin.client import GarminClient, GarminError
from .wellness import get_state, set_state, sync_wellness

PROVIDER = "garmin"
PAGE = 50
MAX_PAGES = 1000

ClientFactory = Callable[[str, str], GarminClient]


def default_client_factory(api_key: str, base_url: str) -> GarminClient:
    return GarminClient(api_key, base_url)


@dataclass
class SyncResult:
    status: str
    new_activities: int = 0
    message: str = ""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _parse_gmt(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value[:19], "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=UTC).isoformat()
    except ValueError:
        return None


def _f(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _insert(conn, item: dict[str, Any], parsed: ParsedActivity, rel_path: str) -> bool:
    source_id = str(item.get("activityId"))
    start = parsed.start_time.isoformat() if parsed.start_time else _parse_gmt(
        item.get("startTimeGMT"))
    if not start:
        return False
    activity_type = item.get("activityType")
    type_key = activity_type.get("typeKey") if isinstance(activity_type, dict) else None
    cur = conn.execute(
        "INSERT OR IGNORE INTO activities (source, source_id, start_time, sport, name, "
        "distance_m, duration_s, elevation_gain_m, avg_hr, max_hr, summary_json, file_path, "
        "has_samples, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            PROVIDER, source_id, start,
            type_key or parsed.sport,
            item.get("activityName"),
            parsed.distance_m if parsed.distance_m is not None else _f(item.get("distance")),
            parsed.duration_s if parsed.duration_s is not None else _f(item.get("duration")),
            parsed.elevation_gain_m if parsed.elevation_gain_m is not None
            else _f(item.get("elevationGain")),
            parsed.avg_hr if parsed.avg_hr is not None else _f(item.get("averageHR")),
            parsed.max_hr if parsed.max_hr is not None else _f(item.get("maxHR")),
            json.dumps(item), rel_path, 1 if parsed.samples else 0, _now(),
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
    return True


def _save_file(path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(content)
    os.replace(tmp, path)


class SyncManager:
    def __init__(self, settings: Settings, box: SecretBox,
                 client_factory: ClientFactory = default_client_factory) -> None:
        self.settings = settings
        self.box = box
        self.client_factory = client_factory
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._lock.locked()

    def start_background(self, mode: str = "quick") -> bool:
        if self._lock.locked():
            return False
        threading.Thread(target=self.run_once, kwargs={"mode": mode}, daemon=True,
                         name="garmin-sync").start()
        return True

    def maybe_run_scheduled(self) -> SyncResult | None:
        """Called every minute by the scheduler; runs a background sync when due."""
        conn = db.connect(self.settings.db_path)
        try:
            has_key = conn.execute("SELECT 1 FROM provider_credentials WHERE provider=?",
                                   (PROVIDER,)).fetchone() is not None
            due = has_key and schedule.is_due(conn, PROVIDER, self.settings)
        finally:
            conn.close()
        return self.run_once(mode="background", scheduled=True) if due else None

    def run_once(self, mode: str = "quick", scheduled: bool = False) -> SyncResult:
        if not self._lock.acquire(blocking=False):
            return SyncResult("error", message="A sync is already running.")
        conn = db.connect(self.settings.db_path)
        run_id = conn.execute(
            "INSERT INTO sync_runs (provider, started_at, status, mode, scheduled) "
            "VALUES (?, ?, 'running', ?, ?)",
            (PROVIDER, _now(), mode, 1 if scheduled else 0),
        ).lastrowid
        conn.commit()
        try:
            result = self._sync(conn, run_id, mode)
        except Exception as exc:  # never leave a run stuck as 'running'
            result = SyncResult("error", message=f"Unexpected error: {type(exc).__name__}")
        conn.execute(
            "UPDATE sync_runs SET finished_at=?, status=?, new_activities=?, message=? WHERE id=?",
            (_now(), result.status, result.new_activities, result.message, run_id),
        )
        conn.commit()
        conn.close()
        self._lock.release()
        return result

    def _sync(self, conn, run_id: int, mode: str) -> SyncResult:
        full = mode == "full"
        lookback = schedule.LOOKBACK_DAYS[mode]
        def progress(text: str) -> None:
            conn.execute("UPDATE sync_runs SET message=? WHERE id=?", (text, run_id))
            conn.commit()

        row = conn.execute(
            "SELECT secret_enc FROM provider_credentials WHERE provider=?", (PROVIDER,)
        ).fetchone()
        if row is None:
            return SyncResult("error", message="No Garmin key configured.")
        try:
            api_key = self.box.decrypt(row["secret_enc"])
            client = self.client_factory(api_key, self.settings.garmin_base_url)
        except (ValueError, GarminError) as exc:
            return SyncResult("error", message=str(exc))

        new = 0
        failures: list[str] = []
        notes: list[str] = []
        try:
            with client:
                client.ensure_token()
                new, failures = self._sync_activities(conn, client, full, lookback, progress)
                earliest = conn.execute(
                    "SELECT MIN(start_time) AS m FROM activities WHERE source=?", (PROVIDER,)
                ).fetchone()["m"]
                floor = (datetime.fromisoformat(earliest).date() - timedelta(days=365)
                         if earliest else date.today() - timedelta(days=730))
                notes = sync_wellness(conn, client, self.settings, full=full,
                                      progress=progress, floor=floor, lookback=lookback)
        except GarminError as exc:
            conn.commit()
            return SyncResult("error", new, f"{exc} ({new} new activities saved before the error; "
                              "run Sync again to continue)")
        msg = f"{new} new activities; health data up to date."
        if failures:
            msg += f" {len(failures)} activities skipped: " + "; ".join(failures[:3])
        if notes:
            msg += " Not available from Garmin: " + "; ".join(notes)
        return SyncResult("ok", new, msg)

    def _sync_activities(self, conn, client, full: bool, lookback: int, progress) -> tuple[int, list[str]]:
        backfilled = get_state(conn, "activities_backfill_done") == "1"
        scan_all = full or not backfilled
        start_date = end_date = None
        if not scan_all:
            latest = conn.execute(
                "SELECT MAX(start_time) AS m FROM activities WHERE source=?", (PROVIDER,)
            ).fetchone()["m"]
            # window starts at the newest stored activity minus the lookback, so a
            # long gap (server off, failed syncs) is covered automatically
            since = (datetime.fromisoformat(latest).date() - timedelta(days=lookback) if latest
                     else date.today() - timedelta(days=self.settings.backfill_days))
            start_date = since.isoformat()
            end_date = (date.today() + timedelta(days=1)).isoformat()

        new = 0
        failures: list[str] = []
        finished = False
        for page in range(MAX_PAGES):
            items = client.search_activities(start=page * PAGE, limit=PAGE,
                                             start_date=start_date, end_date=end_date)
            for item in items:
                source_id = str(item.get("activityId", ""))
                if not source_id.isdecimal():
                    failures.append("activity without a numeric id")
                    continue
                exists = conn.execute(
                    "SELECT 1 FROM activities WHERE source=? AND source_id=?",
                    (PROVIDER, source_id),
                ).fetchone()
                if exists:
                    continue
                try:
                    blob = client.download_activity(source_id)
                    parsed = parse_fit(extract_fit(blob))
                except FitError as exc:
                    failures.append(f"{source_id}: {exc}")
                    continue
                rel = f"activities/{PROVIDER}/{source_id}.zip"
                _save_file(self.settings.data_dir / rel, blob)
                if _insert(conn, item, parsed, rel):
                    new += 1
                conn.commit()
                if new % 10 == 0:
                    progress(f"Downloading activities: {new} new so far")
                time.sleep(self.settings.request_delay_s)
            if len(items) < PAGE:
                finished = True
                break
        if scan_all and finished:
            set_state(conn, "activities_backfill_done", "1")
        return new, failures
