import time

from tests.conftest import API_KEY


def wait_idle(client, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        s = client.get("/api/providers/garmin").json()
        if not s["syncing"] and s["last_sync"] and s["last_sync"]["status"] != "running":
            return s
        time.sleep(0.05)
    raise AssertionError("sync did not finish")


def test_setup_once_then_login_required(client):
    s = client.get("/api/session").json()
    assert s["setup_required"] and not s["authenticated"]
    assert client.get("/api/activities").status_code == 401
    r = client.post("/api/setup", json={"username": "admin", "password": "correct horse battery"})
    assert r.status_code == 200
    assert client.post("/api/setup", json={"username": "x" * 5, "password": "y" * 12}).status_code == 409
    assert client.get("/api/session").json()["authenticated"]
    client.post("/api/logout")
    assert not client.get("/api/session").json()["authenticated"]


def test_login_wrong_password_and_throttle(client):
    client.post("/api/setup", json={"username": "admin", "password": "correct horse battery"})
    client.post("/api/logout")
    for _ in range(5):
        assert client.post("/api/login", json={"username": "admin", "password": "wrong-password-1"}
                           ).status_code == 401
    assert client.post("/api/login", json={"username": "admin", "password": "correct horse battery"}
                       ).status_code == 429


def test_csrf_header_required(settings, fake):
    import httpx
    from fastapi.testclient import TestClient

    from app.garmin.client import GarminClient
    from app.main import create_app
    app = create_app(settings, lambda k, u: GarminClient(k, u, transport=httpx.MockTransport(fake.handler)),
                     start_scheduler=False)
    with TestClient(app) as c:  # no X-Requested-With
        assert c.post("/api/setup", json={"username": "admin", "password": "correct horse battery"}
                      ).status_code == 403


# P1: key is provisioned from a runtime secret file by the Mini-side launcher.
# Tests for the UI being read-only and the key never reaching the DB now live
# in test_key_ui_readonly.py and test_key_not_in_db.py.


def test_sync_end_to_end_and_idempotent(authed, fake, settings):
    assert authed.post("/api/sync").status_code == 202
    s = wait_idle(authed)
    assert s["last_sync"]["status"] == "ok" and s["last_sync"]["new_activities"] == 2
    items = authed.get("/api/activities").json()
    assert items["total"] == 2
    assert {i["sport"] for i in items["items"]} == {"running", "cycling"}
    assert all(i["has_samples"] for i in items["items"])
    assert (settings.data_dir / "activities" / "garmin" / "111.zip").exists()
    downloads = fake.downloads
    authed.post("/api/sync")
    wait_idle(authed)
    assert fake.downloads == downloads  # nothing re-downloaded
    assert authed.get("/api/activities").json()["total"] == 2


def _synced(authed):
    authed.post("/api/sync")
    wait_idle(authed)
    return authed.get("/api/activities").json()["items"]


def test_activity_detail_samples_and_gpx(authed):
    import xml.etree.ElementTree as ET
    items = _synced(authed)
    aid = items[0]["id"]
    d = authed.get(f"/api/activities/{aid}").json()
    assert d["id"] == aid and d["summary"]["activityId"] in (111, 222)
    s = authed.get(f"/api/activities/{aid}/samples?max_points=50").json()
    assert s["total_samples"] == 5 and len(s["t"]) == 5 and s["t"][0] == 0
    assert abs(s["lat"][0] - 49.28) < 1e-3
    g = authed.get(f"/api/activities/{aid}/gpx")
    assert g.status_code == 200 and "gpx" in g.headers["content-type"]
    root = ET.fromstring(g.text)
    ns = {"g": "http://www.topografix.com/GPX/1/1"}
    assert len(root.findall(".//g:trkpt", ns)) == 5
    assert authed.get("/api/activities/99999").status_code == 404


def test_samples_are_downsampled(authed, settings):
    items = _synced(authed)
    aid = items[0]["id"]
    from app import db
    conn = db.connect(settings.db_path)
    conn.executemany(
        "INSERT OR IGNORE INTO samples (activity_id, t, lat, lon, speed) VALUES (?,?,?,?,?)",
        [(aid, 2_000_000_000 + i, 49.0, -123.0, 3.0) for i in range(3000)])
    conn.commit()
    conn.close()
    s = authed.get(f"/api/activities/{aid}/samples?max_points=100").json()
    assert s["total_samples"] >= 3000 and 50 <= len(s["t"]) <= 110


def test_activity_list_since_filter(authed):
    _synced(authed)
    all_ = authed.get("/api/activities").json()
    assert all_["total"] == 2
    cut = authed.get("/api/activities?since=2999-01-01").json()
    assert cut["total"] == 0 and cut["items"] == []


def test_concurrent_requests_do_not_hit_sqlite_thread_errors(authed):
    from concurrent.futures import ThreadPoolExecutor

    def hit(_):
        return authed.get("/api/activities").status_code

    with ThreadPoolExecutor(16) as pool:
        codes = list(pool.map(hit, range(200)))
    assert set(codes) == {200}
