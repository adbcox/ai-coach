def test_default_sport_preference(authed):
    assert authed.get("/api/preferences").json()["default_sport"] == "Running"
    r = authed.put("/api/preferences", json={"default_sport": "Cycling"})
    assert r.status_code == 200 and r.json()["default_sport"] == "Cycling"
    assert authed.get("/api/preferences").json()["default_sport"] == "Cycling"
    assert authed.put("/api/preferences", json={"default_sport": "Basketball"}).status_code == 400
    assert authed.get("/api/preferences").json()["default_sport"] == "Cycling"
    authed.put("/api/preferences", json={"default_sport": "All"})
    assert authed.get("/api/preferences").json()["default_sport"] == "All"


def test_preferences_require_login(client):
    assert client.get("/api/preferences").status_code == 401
    assert client.put("/api/preferences", json={"default_sport": "All"}).status_code == 401


def test_preference_survives_backup_and_restore(tmp_path):
    from tests.test_backup import make_client, wait_backup
    a, _ = make_client(tmp_path / "a")
    with a:
        a.post("/api/setup", json={"username": "admin", "password": "correct horse battery"})
        a.put("/api/preferences", json={"default_sport": "Hiking"})
        a.post("/api/backups", json={})
        data = a.get("/api/backups/" + wait_backup(a)["items"][0]["name"]).content
    b, _ = make_client(tmp_path / "b")
    with b:
        assert b.put("/api/restore", content=data).status_code == 200
        b.post("/api/login", json={"username": "admin", "password": "correct horse battery"})
        assert b.get("/api/preferences").json()["default_sport"] == "Hiking"
