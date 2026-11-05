"""Garmin account-export importer — exercised with CSV wellness files.

FIT-walk paths share logic with Strava's and are covered by the dedup test.
Here we only verify the CSV → wellness_raw pipeline that is unique to the
Garmin export importer.
"""

from __future__ import annotations

import io
import zipfile

from app import db
from app.config import Settings
from app.importers import garmin_export


def _zip_with_csvs(tmp_path):
    archive = tmp_path / "garmin_export.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "Wellness/Sleep_2026-10.csv",
            "date,duration_min,score\n"
            "2026-10-01,420,78\n"
            "2026-10-02,445,85\n",
        )
        zf.writestr(
            "Wellness/HRV_2026-10.csv",
            "date,lastNightAvg\n2026-10-01,52\n2026-10-02,55\n",
        )
        zf.writestr(
            "Wellness/UnknownThing_2026-10.csv",
            "date,foo\n2026-10-01,1\n",
        )
    archive.write_bytes(buf.getvalue())
    return archive


def test_import_wellness_csvs(tmp_path):
    settings = Settings(data_dir=tmp_path, request_delay_s=0)
    archive = _zip_with_csvs(tmp_path)
    stats = garmin_export.run(archive, tmp_path)
    assert stats.wellness_rows == 4  # sleep × 2 + hrv × 2
    conn = db.connect(settings.db_path)
    kinds = sorted({r[0] for r in conn.execute(
        "SELECT DISTINCT kind FROM wellness_raw WHERE source='garmin_export'"
    )})
    assert kinds == ["export_hrv", "export_sleep"]
    rows = conn.execute(
        "SELECT kind, start_date, payload FROM wellness_raw "
        "WHERE source='garmin_export' AND kind='export_sleep' "
        "ORDER BY start_date"
    ).fetchall()
    assert [r["start_date"] for r in rows] == ["2026-10-01", "2026-10-02"]
    # The payload is JSON and includes the raw CSV row(s) for that date.
    import json
    payload = json.loads(rows[0]["payload"])
    assert payload["file"].startswith("Sleep_")
    assert payload["rows"][0]["score"] == "78"


def test_unknown_csv_kinds_are_skipped(tmp_path):
    archive = _zip_with_csvs(tmp_path)
    garmin_export.run(archive, tmp_path)
    conn = db.connect(Settings(data_dir=tmp_path, request_delay_s=0).db_path)
    # UnknownThing_*.csv must not have produced any rows.
    row = conn.execute(
        "SELECT COUNT(*) FROM wellness_raw "
        "WHERE source='garmin_export' AND kind LIKE 'export_%unknown%'"
    ).fetchone()
    assert row[0] == 0
