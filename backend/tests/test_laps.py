import pytest

from app import db, laps
from app.fit.parser import FitError, parse_fit, parse_laps
from tests.conftest import API_KEY
from tests.fitgen import make_fit, make_zip
from tests.test_api import wait_idle

AUTO = [{"secs": 300, "dist": 1000, "hr": 150, "hrmax": 158, "cad": 86, "up": 10, "down": 4},
        {"secs": 290, "dist": 1000, "hr": 155, "hrmax": 163, "cad": 87, "up": 2, "down": 9},
        {"secs": 150, "dist": 430, "hr": 160, "hrmax": 171, "cad": 88, "up": 0, "down": 1}]  # the short last split
WORKOUT = [{"secs": 600, "dist": 1800, "intensity": 2, "trigger": 1}, {"secs": 240, "dist": 1000, "intensity": 5, "trigger": 0},
           {"secs": 120, "dist": 300, "intensity": 1, "trigger": 0}, {"secs": 300, "dist": 900, "intensity": 3, "trigger": 0}]


def test_parse_laps_reads_garmin_split_fields():
    got = parse_laps(make_fit(laps=AUTO))
    assert [round(lap.distance_m) for lap in got] == [1000, 1000, 430]
    assert got[0].timer_s == 300 and got[0].avg_hr == 150 and got[0].max_hr == 158 and got[0].avg_cadence == 86
    assert got[0].ascent_m == 10 and got[0].descent_m == 4 and got[0].trigger == "distance" and got[0].intensity == "active"
    assert got[0].avg_speed == pytest.approx(1000 / 300, rel=0.01)
    assert parse_fit(make_fit(laps=AUTO)).laps[2].index == 2
    assert parse_laps(make_fit()) == []
    with pytest.raises(FitError):
        parse_laps(b"not a fit file")


def sync_with(authed, fake, fit):
    fake.fit = fit
    authed.put("/api/providers/garmin", json={"api_key": API_KEY})
    assert authed.post("/api/sync").status_code == 202
    wait_idle(authed)
    return authed.get("/api/activities").json()["items"]


def test_laps_are_stored_on_download_and_served(authed, fake):
    items = sync_with(authed, fake, lambda: make_fit(laps=AUTO))
    aid = next(i["id"] for i in items if i["sport"] == "running")
    r = authed.get(f"/api/activities/{aid}/laps").json()
    assert r["scanned"] and r["count"] == 3 and r["kind"] == "auto_distance" and r["auto_distance_m"] == 1000
    first, last = r["laps"][0], r["laps"][2]
    assert first["n"] == 1 and first["distance_m"] == 1000 and first["time_s"] == 300 and round(first["pace_s_per_km"]) == 300
    assert first["cadence_spm"] == 172  # strides per minute x 2 = steps per minute for running
    assert last["distance_m"] == 430 and last["start_offset_s"] == 590
    assert r["fastest_lap"] == 2 and r["slowest_lap"] == 1  # the 430 m remainder is too short to rank
    assert authed.get("/api/activities/99999/laps").status_code == 404


def test_workout_laps_are_labelled(authed, fake):
    items = sync_with(authed, fake, lambda: make_fit(laps=WORKOUT))
    aid = items[0]["id"]
    r = authed.get(f"/api/activities/{aid}/laps").json()
    assert r["kind"] == "workout" and [lap["intensity"] for lap in r["laps"]] == ["warmup", "interval", "rest", "cooldown"]
    assert authed.get("/api/activities").json()["total"] >= 1


def test_activities_stored_before_laps_were_kept_are_backfilled_from_the_file_on_disk(authed, fake, settings):
    items = sync_with(authed, fake, lambda: make_fit())  # no lap messages at download time
    aid = items[0]["id"]
    assert authed.get(f"/api/activities/{aid}/laps").json()["count"] == 0
    conn = db.connect(settings.db_path)
    path = settings.data_dir / conn.execute("SELECT file_path FROM activities WHERE id=?", (aid,)).fetchone()["file_path"]
    path.write_bytes(make_zip(make_fit(laps=AUTO)))                 # the stored file has laps (as if parsed by a newer app)
    conn.execute("DELETE FROM lap_scan")                              # an install that upgraded: nothing scanned yet
    conn.commit()
    assert aid in laps.pending(conn)
    assert laps.scan_pending(conn, settings) >= 1 and laps.pending(conn) == []
    assert authed.get(f"/api/activities/{aid}/laps").json()["count"] == 3
    laps.scan_pending(conn, settings)
    assert conn.execute("SELECT COUNT(*) n FROM laps WHERE activity_id=?", (aid,)).fetchone()["n"] == 3  # idempotent
    conn.close()


def test_missing_or_broken_file_is_marked_scanned_not_retried(authed, fake, settings):
    items = sync_with(authed, fake, lambda: make_fit())
    aid = items[0]["id"]
    conn = db.connect(settings.db_path)
    path = settings.data_dir / conn.execute("SELECT file_path FROM activities WHERE id=?", (aid,)).fetchone()["file_path"]
    conn.execute("DELETE FROM lap_scan")
    conn.commit()
    path.unlink()
    laps.scan_pending(conn, settings)
    assert laps.pending(conn) == []
    assert authed.get(f"/api/activities/{aid}/laps").json()["count"] == 0
    conn.close()


def test_laps_require_login(client):
    assert client.get("/api/activities/1/laps").status_code == 401
