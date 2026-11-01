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


def test_bad_key_rejected_and_not_stored(authed):
    r = authed.put("/api/providers/garmin", json={"api_key": "wrong-key-123456"})
    assert r.status_code == 400
    assert authed.get("/api/providers/garmin").json()["configured"] is False


def test_key_encrypted_at_rest_and_never_returned(authed, settings):
    r = authed.put("/api/providers/garmin", json={"api_key": API_KEY})
    assert r.status_code == 200 and API_KEY not in r.text
    assert API_KEY not in authed.get("/api/providers/garmin").text
    for path in settings.data_dir.rglob("*"):
        if path.is_file() and path.name != "master.key":
            assert API_KEY.encode() not in path.read_bytes(), path


def test_sync_end_to_end_and_idempotent(authed, fake, settings):
    assert authed.post("/api/sync").status_code == 400  # no key yet
    authed.put("/api/providers/garmin", json={"api_key": API_KEY})
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


def test_key_removal(authed):
    authed.put("/api/providers/garmin", json={"api_key": API_KEY})
    assert authed.delete("/api/providers/garmin").json()["configured"] is False
