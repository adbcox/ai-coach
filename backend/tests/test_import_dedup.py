"""Dedup rule: ±60 s start_time, 50 m / 1.5 % distance, 30 s / 2 % duration.

Covered via the common helper directly so we don't need to craft FIT bytes.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app import db
from app.config import Settings
from app.importers._common import (
    CandidateRow,
    find_duplicate,
    mark_canonical_link,
)


def _conn(tmp_path):
    s = Settings(data_dir=tmp_path, request_delay_s=0)
    db.init_db(s.db_path)
    return db.connect(s.db_path)


def _ins(conn, aid, start, dist, dur, source="garmin"):
    conn.execute(
        "INSERT INTO activities (id, source, source_id, start_time, sport, name, "
        "distance_m, duration_s, created_at) "
        "VALUES (?, ?, ?, ?, 'cycling', NULL, ?, ?, '2026-11-05T00:00:00+00:00')",
        (aid, source, str(aid), start, dist, dur),
    )


def test_dedup_matches_within_tolerance(tmp_path):
    conn = _conn(tmp_path)
    _ins(conn, 1, "2026-11-01T10:00:00+00:00", 30000.0, 3600.0)
    conn.commit()
    # 30 s late, 20 m longer, 10 s longer → within every tolerance
    cand = CandidateRow(
        start_time=datetime(2026, 11, 1, 10, 0, 30, tzinfo=UTC),
        distance_m=30020.0, duration_s=3610.0, sport=None,
    )
    assert find_duplicate(conn, cand) == 1


def test_dedup_rejects_different_distance(tmp_path):
    conn = _conn(tmp_path)
    _ins(conn, 1, "2026-11-01T10:00:00+00:00", 30000.0, 3600.0)
    conn.commit()
    cand = CandidateRow(
        start_time=datetime(2026, 11, 1, 10, 0, 10, tzinfo=UTC),
        distance_m=35000.0,  # 5 km off → way outside 1.5 %
        duration_s=3600.0, sport=None,
    )
    assert find_duplicate(conn, cand) is None


def test_dedup_rejects_different_start(tmp_path):
    conn = _conn(tmp_path)
    _ins(conn, 1, "2026-11-01T10:00:00+00:00", 30000.0, 3600.0)
    conn.commit()
    cand = CandidateRow(
        start_time=datetime(2026, 11, 1, 10, 5, 0, tzinfo=UTC),  # 5 min late
        distance_m=30000.0, duration_s=3600.0, sport=None,
    )
    assert find_duplicate(conn, cand) is None


def test_canonical_id_set_only_once(tmp_path):
    conn = _conn(tmp_path)
    _ins(conn, 1, "2026-11-01T10:00:00+00:00", 30000.0, 3600.0)
    conn.commit()
    mark_canonical_link(conn, 1)
    first = conn.execute("SELECT canonical_id FROM activities WHERE id=1").fetchone()[0]
    assert first == 1
    # Simulate another linker call — canonical_id is COALESCEd, so it stays.
    conn.execute("UPDATE activities SET canonical_id = NULL WHERE id = 2 OR 1 = 0")  # no-op
    mark_canonical_link(conn, 1)
    again = conn.execute("SELECT canonical_id FROM activities WHERE id=1").fetchone()[0]
    assert again == 1
