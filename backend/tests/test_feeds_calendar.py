"""Calendar ICS feed: fetches, parses VEVENTs, classifies travel/busy."""

from __future__ import annotations

import httpx

from app import db
from app.config import Settings
from app.feeds import calendar_ics


_ICS = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:evt-1@test
SUMMARY:Flight to NYC
DTSTART:20261110T120000Z
DTEND:20261110T150000Z
END:VEVENT
BEGIN:VEVENT
UID:evt-2@test
SUMMARY:1:1 with manager
DTSTART:20261110T160000Z
DTEND:20261110T163000Z
END:VEVENT
BEGIN:VEVENT
UID:evt-3@test
SUMMARY:Lunch
DTSTART:20261110T120000Z
DTEND:20261110T130000Z
END:VEVENT
BEGIN:VEVENT
UID:evt-4@test
SUMMARY:All day thing
DTSTART:20261111
DTEND:20261112
END:VEVENT
END:VCALENDAR
"""


def _settings(tmp_path):
    url_file = tmp_path / "ics_url"
    url_file.write_text("https://example.invalid/private.ics")
    return Settings(data_dir=tmp_path, request_delay_s=0,
                    calendar_ics_url_file=url_file)


def test_classifies_travel_and_busy(tmp_path):
    s = _settings(tmp_path)
    db.init_db(s.db_path)
    conn = db.connect(s.db_path)

    def handler(request):
        return httpx.Response(200, text=_ICS)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        stats = calendar_ics.sync(conn, s, client=client)
    assert stats.inserted == 4
    rows = {r["id"]: r for r in conn.execute(
        "SELECT id, day, is_travel, is_busy FROM calendar_events"
    )}
    assert rows["evt-1@test"]["is_travel"] == 1
    assert rows["evt-1@test"]["is_busy"] == 1          # 3h long → busy
    assert rows["evt-2@test"]["is_busy"] == 1          # "1:1" matches denylist
    assert rows["evt-2@test"]["is_travel"] == 0
    assert rows["evt-3@test"]["is_busy"] == 0          # 1h plain lunch
    assert rows["evt-3@test"]["is_travel"] == 0
    # All-day event parses the DTSTART as YYYYMMDD → day matches.
    assert rows["evt-4@test"]["day"] == "2026-11-11"


def test_rerun_updates(tmp_path):
    s = _settings(tmp_path)
    db.init_db(s.db_path)
    conn = db.connect(s.db_path)

    def handler(request):
        return httpx.Response(200, text=_ICS)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        calendar_ics.sync(conn, s, client=client)
        stats = calendar_ics.sync(conn, s, client=client)
    assert stats.updated == 4
    assert stats.inserted == 0


def test_disabled_without_file(tmp_path):
    s = Settings(data_dir=tmp_path, request_delay_s=0)
    db.init_db(s.db_path)
    conn = db.connect(s.db_path)
    stats = calendar_ics.sync(conn, s)
    assert stats.inserted == 0
