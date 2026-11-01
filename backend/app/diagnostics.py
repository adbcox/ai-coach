"""Privacy-preserving description of the stored Garmin data.

Produces field names, types, value ranges and fill rates, so the app's author
can see what Garmin actually returns without seeing personal values. Strings
are never included (except a small allowlist of enum-like keys); GPS
coordinates, names and dates are reduced to types or coarse ranges.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from typing import Any

from . import __version__

ENUM_KEYS = {
    "typeKey", "sportTypeKey", "sport", "subSport", "unit", "status", "type",
    "trainingEffectLabel", "aerobicTrainingEffectMessage", "anaerobicTrainingEffectMessage",
    "feedback", "qualifier", "overallScore", "stressQualifier", "sleepScoreFeedback",
}
SAMPLE_LIMIT = 200          # payloads inspected per data type
MAX_ENUM_VALUES = 12
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")
_COORD_KEYS = re.compile(r"lat|lon|long|position|gps|polyline|location|address|name|email", re.I)
# Numeric fields whose min/max would identify the account, the device, the timeline or the
# body (IDs, timestamps, weight and body composition). Types and counts are still shown.
_PRIVATE_NUM_KEYS = re.compile(
    r"(^|[a-z0-9_])(id|pk|uuid)$|userprofile|owner|device|samplepk|timestamp|time(gmt|local)?$|"
    r"date|^from$|^until$|created|begin|weight|bmi|bodyfat|bodywater|bonemass|musclemass|"
    r"visceral|metabolicage|height", re.I)
_BIG = 1_000_000_000  # anything this large is an epoch time or an id, never a training value


class Shape:
    def __init__(self) -> None:
        self.paths: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"types": Counter(), "n": 0, "min": None, "max": None, "len": [None, None],
                     "enum": Counter()})
        self.docs = 0

    def add(self, value: Any) -> None:
        self.docs += 1
        self._walk(value, "$", "")

    def _walk(self, value: Any, path: str, key: str) -> None:
        slot = self.paths[path]
        slot["n"] += 1
        if value is None:
            slot["types"]["null"] += 1
        elif isinstance(value, bool):
            slot["types"]["bool"] += 1
        elif isinstance(value, (int, float)):
            slot["types"]["number"] += 1
            if not (_COORD_KEYS.search(key) or _PRIVATE_NUM_KEYS.search(key) or abs(value) >= _BIG):
                slot["min"] = value if slot["min"] is None else min(slot["min"], value)
                slot["max"] = value if slot["max"] is None else max(slot["max"], value)
        elif isinstance(value, str):
            if _DATETIME.match(value):
                slot["types"]["datetime-string"] += 1
            elif _DATE.match(value):
                slot["types"]["date-string"] += 1
            else:
                slot["types"]["string"] += 1
                if key in ENUM_KEYS and len(value) <= 60 and len(slot["enum"]) < MAX_ENUM_VALUES:
                    slot["enum"][value] += 1
        elif isinstance(value, list):
            slot["types"]["list"] += 1
            n = len(value)
            lo, hi = slot["len"]
            slot["len"] = [n if lo is None else min(lo, n), n if hi is None else max(hi, n)]
            for item in value[:50]:
                self._walk(item, path + "[]", key)
        elif isinstance(value, dict):
            slot["types"]["object"] += 1
            for k, v in value.items():
                self._walk(v, f"{path}.{k}", str(k))

    def render(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for path in sorted(self.paths):
            s = self.paths[path]
            entry: dict[str, Any] = {
                "seen_in": s["n"],
                "types": dict(s["types"]),
            }
            if s["min"] is not None:
                entry["range"] = [s["min"], s["max"]]
            if s["len"][0] is not None:
                entry["list_length"] = s["len"]
            if s["enum"]:
                entry["values"] = dict(s["enum"])
            out[path] = entry
        return {"documents": self.docs, "fields": out}


def build(conn) -> dict[str, Any]:
    report: dict[str, Any] = {"app_version": __version__, "note": (
        "Structure only. No names, GPS coordinates, ids, timestamps, dates or body measurements. Other numeric fields (distance, heart rate, ...) show min/max across records."), }

    counts = conn.execute(
        "SELECT sport, COUNT(*) AS n FROM activities GROUP BY sport ORDER BY n DESC").fetchall()
    first_last = conn.execute(
        "SELECT MIN(start_time) AS a, MAX(start_time) AS b, COUNT(*) AS n FROM activities").fetchone()
    report["activities"] = {
        "count": first_last["n"],
        "span_months": [str(first_last["a"] or "")[:7], str(first_last["b"] or "")[:7]],
        "by_sport": {str(r["sport"]): r["n"] for r in counts},
    }

    shape = Shape()
    for row in conn.execute(
            "SELECT summary_json FROM activities ORDER BY start_time DESC LIMIT ?", (SAMPLE_LIMIT,)):
        try:
            shape.add(json.loads(row["summary_json"] or "null"))
        except ValueError:
            continue
    report["activity_list_item"] = shape.render()

    cols = ["lat", "lon", "alt", "hr", "cadence", "power", "speed", "dist"]
    total = conn.execute("SELECT COUNT(*) AS n FROM samples").fetchone()["n"]
    fill = {}
    if total:
        for c in cols:
            n = conn.execute(f"SELECT COUNT({c}) AS n FROM samples").fetchone()["n"]  # noqa: S608
            fill[c] = round(n / total, 3)
    per_act = conn.execute(
        "SELECT COUNT(*) AS acts, AVG(c) AS avg_samples, MAX(c) AS max_samples FROM "
        "(SELECT COUNT(*) AS c FROM samples GROUP BY activity_id)").fetchone()
    report["fit_samples"] = {
        "total_rows": total, "fill_rate": fill,
        "activities_with_samples": per_act["acts"],
        "avg_samples_per_activity": round(per_act["avg_samples"] or 0, 1),
        "max_samples_per_activity": per_act["max_samples"],
        "activities_without_samples": conn.execute(
            "SELECT COUNT(*) AS n FROM activities WHERE has_samples=0").fetchone()["n"],
    }

    health: dict[str, Any] = {}
    kinds = conn.execute(
        "SELECT kind, COUNT(*) AS rows_, SUM(is_empty) AS empty, MIN(start_date) AS a, "
        "MAX(start_date) AS b FROM wellness_raw GROUP BY kind ORDER BY kind").fetchall()
    for k in kinds:
        shape = Shape()
        for row in conn.execute(
                "SELECT payload FROM wellness_raw WHERE kind=? AND is_empty=0 "
                "ORDER BY start_date DESC LIMIT ?", (k["kind"], SAMPLE_LIMIT)):
            try:
                shape.add(json.loads(row["payload"]))
            except ValueError:
                continue
        health[k["kind"]] = {
            "records": k["rows_"], "empty": k["empty"] or 0,
            "span_months": [str(k["a"])[:7], str(k["b"])[:7]],
            **shape.render(),
        }
    report["health"] = health

    report["sync_runs"] = [
        {"status": r["status"], "new_activities": r["new_activities"], "message": r["message"]}
        for r in conn.execute(
            "SELECT status, new_activities, message FROM sync_runs ORDER BY id DESC LIMIT 5")]
    return report
