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


def test_max_hr_zones_auto_and_custom(authed, settings):
    from app import db
    base = authed.get("/api/preferences").json()
    assert base["max_hr"] is None and base["hr_zones"] == []
    conn = db.connect(settings.db_path)
    conn.execute("INSERT INTO activities (source, source_id, start_time, max_hr, created_at) VALUES "
                 "('garmin','1','2026-01-01T00:00:00+00:00',186,'x'), "
                 "('garmin','2','2026-01-02T00:00:00+00:00',0,'x')")
    conn.commit()
    conn.close()
    auto = authed.get("/api/preferences").json()
    assert auto["max_hr"] == 186 and auto["max_hr_source"] == "auto" and auto["max_hr_auto"] == 186
    assert [z["zone"] for z in auto["hr_zones"]] == [1, 2, 3, 4, 5]
    assert auto["hr_zones"][0]["low"] == 93 and auto["hr_zones"][4]["high"] == 186
    custom = authed.put("/api/preferences", json={"max_hr": 190}).json()
    assert custom["max_hr"] == 190 and custom["max_hr_source"] == "custom"
    assert custom["default_sport"] == "Running"  # untouched
    assert authed.put("/api/preferences", json={"max_hr": 50}).status_code == 422
    cleared = authed.put("/api/preferences", json={"max_hr": None}).json()
    assert cleared["max_hr"] == 186 and cleared["max_hr_source"] == "auto"
