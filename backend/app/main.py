"""FastAPI application: auth, Garmin key settings, sync, activities, static SPA."""

from __future__ import annotations

import asyncio
import contextlib
import json as _json
import os
import time
import uuid
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, backup, db, diagnostics, recovery, schedule, security, smb
from .config import Settings
from .crypto import SecretBox
from .garmin.client import GarminError
from .gpx import build_gpx
from .sync import PROVIDER, ClientFactory, SyncManager, default_client_factory

COOKIE = "aec_session"
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "aec"
_MAX_FAILS, _WINDOW_S = 5, 300


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=256)


class Schedule(BaseModel):
    interval_minutes: int


class SmbConfig(BaseModel):
    host: str = Field(min_length=1, max_length=253)
    port: int = Field(default=445, ge=1, le=65535)
    share: str = Field(min_length=1, max_length=80)
    folder: str = Field(default="", max_length=200)
    username: str = Field(min_length=1, max_length=128)
    domain: str | None = Field(default=None, max_length=128)
    password: str | None = Field(default=None, max_length=256)
    interval_minutes: int = 1440
    keep: int = Field(default=14, ge=1, le=365)


class BackupRequest(BaseModel):
    passphrase: str | None = Field(default=None, max_length=256)


class GarminKey(BaseModel):
    api_key: str = Field(min_length=8, max_length=4096)


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def create_app(
    settings: Settings | None = None,
    client_factory: ClientFactory = default_client_factory,
    *,
    start_scheduler: bool = True,
) -> FastAPI:
    settings = settings or Settings.from_env()
    db.init_db(settings.db_path)
    box = SecretBox.load(settings.secrets_dir, settings.app_secret)
    _conn = db.connect(settings.db_path)
    try:  # a restart kills any running sync; do not leave its row "running" forever
        _conn.execute(
            "UPDATE sync_runs SET status='error', finished_at=?, message=COALESCE(message, '') || "
            "' (interrupted: the server restarted; run Sync again to continue)' WHERE status='running'",
            (_now(),))
        _conn.commit()
    finally:
        _conn.close()
    manager = SyncManager(settings, box, client_factory)
    failures: dict[str, list[float]] = defaultdict(list)
    backups = backup.BackupManager(settings, box)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI):
        task = None
        if start_scheduler:
            async def loop() -> None:
                while True:
                    await asyncio.sleep(60)
                    try:
                        await asyncio.to_thread(manager.maybe_run_scheduled)
                        await asyncio.to_thread(backups.maybe_run_scheduled)
                    except Exception:  # keep the scheduler alive whatever happens
                        pass
            task = asyncio.create_task(loop())
        yield
        if task:
            task.cancel()

    def csrf_guard(request: Request) -> None:
        if request.method not in ("GET", "HEAD", "OPTIONS") and (
            request.headers.get(CSRF_HEADER) != CSRF_VALUE
        ):
            raise HTTPException(403, "Missing X-Requested-With header.")

    app = FastAPI(title="ai-endurance-coach", version=__version__, lifespan=lifespan,
                  dependencies=[Depends(csrf_guard)], docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.sync_manager = manager
    app.state.backup_manager = backups

    def get_conn() -> Iterator:
        conn = db.connect(settings.db_path)
        try:
            yield conn
        finally:
            conn.close()

    def current_user(request: Request, conn=Depends(get_conn)):
        user = security.lookup_session(conn, request.cookies.get(COOKIE))
        if user is None:
            raise HTTPException(401, "Not signed in.")
        return user

    def start_session(response: Response, conn, user_id: int) -> None:
        token = security.create_session(conn, user_id, settings.session_days)
        response.set_cookie(COOKIE, token, httponly=True, samesite="lax",
                            secure=settings.secure_cookies, max_age=settings.session_days * 86400,
                            path="/")

    build_id = (os.environ.get("AEC_BUILD") or "dev")[:7]

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__, "build": build_id}

    @app.get("/api/session")
    def session(request: Request, conn=Depends(get_conn)) -> dict:
        users = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        user = security.lookup_session(conn, request.cookies.get(COOKIE))
        return {"setup_required": users == 0, "authenticated": user is not None,
                "username": user["username"] if user else None}

    @app.post("/api/setup")
    def setup(body: Credentials, response: Response, conn=Depends(get_conn)) -> dict:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]:
            conn.rollback()
            raise HTTPException(409, "Setup already completed.")
        user_id = conn.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (body.username.strip(), security.hash_password(body.password), _now()),
        ).lastrowid
        conn.commit()
        start_session(response, conn, user_id)
        return {"ok": True}

    @app.post("/api/login")
    def login(body: Credentials, request: Request, response: Response,
              conn=Depends(get_conn)) -> dict:
        ip = request.client.host if request.client else "unknown"
        now = time.time()
        failures[ip] = [t for t in failures[ip] if now - t < _WINDOW_S]
        if len(failures[ip]) >= _MAX_FAILS:
            raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")
        row = conn.execute("SELECT id, password_hash FROM users WHERE username = ?",
                           (body.username.strip(),)).fetchone()
        ok = security.verify_password(body.password, row["password_hash"]) if row else False
        if not ok:
            failures[ip].append(now)
            raise HTTPException(401, "Wrong username or password.")
        failures.pop(ip, None)
        start_session(response, conn, row["id"])
        return {"ok": True}

    @app.post("/api/logout")
    def logout(request: Request, response: Response, conn=Depends(get_conn)) -> dict:
        security.delete_session(conn, request.cookies.get(COOKIE))
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    def schedule_status(conn) -> dict:
        nxt = schedule.next_run(conn, PROVIDER, settings)
        return {"interval_minutes": schedule.get_interval(conn, PROVIDER, settings),
                "options": schedule.INTERVAL_OPTIONS,
                "next_run_at": nxt.isoformat(timespec="seconds") if nxt else None}

    def garmin_status(conn) -> dict:
        cred = conn.execute("SELECT updated_at, validated_at FROM provider_credentials "
                            "WHERE provider=?", (PROVIDER,)).fetchone()
        last = conn.execute("SELECT started_at, finished_at, status, new_activities, message, mode, scheduled "
                            "FROM sync_runs WHERE provider=? ORDER BY id DESC LIMIT 1",
                            (PROVIDER,)).fetchone()
        acts = conn.execute("SELECT COUNT(*) AS n, MIN(start_time) AS first, "
                            "MAX(start_time) AS last FROM activities").fetchone()
        health = {r["kind"]: r["n"] for r in conn.execute(
            "SELECT kind, COUNT(*) AS n FROM wellness_raw WHERE is_empty=0 GROUP BY kind")}
        return {
            "stored": {"activities": acts["n"], "first_activity": acts["first"],
                       "last_activity": acts["last"], "health_records": health},
            "schedule": schedule_status(conn),
            "configured": cred is not None,
            "validated_at": cred["validated_at"] if cred else None,
            "syncing": manager.running,
            "last_sync": dict(last) if last else None,
        }

    @app.get("/api/providers/garmin")
    def garmin_get(_=Depends(current_user), conn=Depends(get_conn)) -> dict:
        return garmin_status(conn)

    @app.put("/api/providers/garmin")
    def garmin_put(body: GarminKey, _=Depends(current_user), conn=Depends(get_conn)) -> dict:
        try:
            client = client_factory(body.api_key, settings.garmin_base_url)
            with client:
                client.ensure_token()  # validates the key with Garmin
        except GarminError as exc:
            raise HTTPException(400, str(exc)) from exc
        now = _now()
        conn.execute(
            "INSERT INTO provider_credentials (provider, secret_enc, updated_at, validated_at) "
            "VALUES (?, ?, ?, ?) ON CONFLICT(provider) DO UPDATE SET secret_enc=excluded."
            "secret_enc, updated_at=excluded.updated_at, validated_at=excluded.validated_at",
            (PROVIDER, box.encrypt(body.api_key.strip()), now, now),
        )
        conn.commit()
        return garmin_status(conn)

    @app.delete("/api/providers/garmin")
    def garmin_delete(_=Depends(current_user), conn=Depends(get_conn)) -> dict:
        conn.execute("DELETE FROM provider_credentials WHERE provider=?", (PROVIDER,))
        conn.commit()
        return garmin_status(conn)

    @app.put("/api/providers/garmin/schedule")
    def garmin_schedule(body: Schedule, _=Depends(current_user), conn=Depends(get_conn)) -> dict:
        try:
            schedule.set_interval(conn, PROVIDER, body.interval_minutes)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return garmin_status(conn)

    @app.post("/api/sync", status_code=202)
    def sync_start(mode: str = "quick", full: bool = False, _=Depends(current_user),
                   conn=Depends(get_conn)) -> dict:
        mode = "full" if full else mode
        if mode not in schedule.MODES:
            raise HTTPException(400, "mode must be quick, background or full.")
        if conn.execute("SELECT 1 FROM provider_credentials WHERE provider=?",
                        (PROVIDER,)).fetchone() is None:
            raise HTTPException(400, "Add your Garmin key in Settings first.")
        if not manager.start_background(mode=mode):
            raise HTTPException(409, "A sync is already running.")
        return {"started": True}

    @app.get("/api/backups")
    def backups_list(_=Depends(current_user), conn=Depends(get_conn)) -> dict:
        return {"items": backup.list_backups(settings), "running": backups.lock.locked(),
                "error": backups.error, "keep": backup.DEFAULT_KEEP,
                "smb": backup.target_status(conn, box)}

    @app.post("/api/backups", status_code=202)
    def backups_create(body: BackupRequest, _=Depends(current_user)) -> dict:
        if not backups.start_background(body.passphrase):
            raise HTTPException(409, "A backup is already running.")
        return {"started": True}

    @app.put("/api/backups/smb")
    def backups_smb_put(body: SmbConfig, _=Depends(current_user), conn=Depends(get_conn)) -> dict:
        existing = backup.load_target(conn, box)
        password = body.password or (existing[0].password if existing else "")
        if not password:
            raise HTTPException(400, "Password is required.")
        if body.interval_minutes not in backup.BACKUP_INTERVALS:
            raise HTTPException(400, "Unsupported interval.")
        target = smb.SmbTarget(host=body.host.strip(), share=body.share.strip(),
                               folder=body.folder.strip(), username=body.username.strip(),
                               password=password, domain=(body.domain or "").strip() or None,
                               port=body.port)
        try:
            smb.check_connection(target)  # sign in and prove the folder is writable
        except smb.SmbError as exc:
            raise HTTPException(400, str(exc)) from exc
        backup.save_target(conn, box, host=target.host, port=target.port, share=target.share,
                           folder=target.folder, username=target.username, domain=target.domain,
                           password=password, interval_minutes=body.interval_minutes,
                           keep=body.keep)
        return backup.target_status(conn, box)

    @app.delete("/api/backups/smb")
    def backups_smb_delete(_=Depends(current_user), conn=Depends(get_conn)) -> dict:
        conn.execute("DELETE FROM backup_target WHERE id=1")
        conn.commit()
        return backup.target_status(conn, box)

    @app.get("/api/backups/{name}")
    def backups_download(name: str, _=Depends(current_user)) -> FileResponse:
        path = backup.resolve(settings, name)
        if path is None:
            raise HTTPException(404, "Backup not found.")
        return FileResponse(path, media_type="application/x-tar", filename=name)

    @app.delete("/api/backups/{name}")
    def backups_delete(name: str, _=Depends(current_user)) -> dict:
        path = backup.resolve(settings, name)
        if path is None:
            raise HTTPException(404, "Backup not found.")
        path.unlink()
        return {"ok": True}

    @app.put("/api/restore")
    async def restore(request: Request) -> dict:
        def who() -> tuple[int, bool]:
            conn = db.connect(settings.db_path)
            try:
                users = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
                user = security.lookup_session(conn, request.cookies.get(COOKIE))
                return users, user is not None
            finally:
                conn.close()

        users, signed_in = await asyncio.to_thread(who)
        if users and not signed_in:
            raise HTTPException(401, "Sign in to restore a backup.")
        if not manager.try_exclusive():
            raise HTTPException(409, "A sync is running. Try again when it finishes.")
        if not backups.lock.acquire(blocking=False):
            manager.release_exclusive()
            raise HTTPException(409, "A backup is running. Try again when it finishes.")
        upload = settings.data_dir / "tmp" / f"upload-{uuid.uuid4().hex}.tar"
        try:
            upload.parent.mkdir(parents=True, exist_ok=True)
            with open(upload, "wb") as handle:
                async for chunk in request.stream():
                    handle.write(chunk)
            passphrase = request.headers.get("x-passphrase") or None
            try:
                summary = await asyncio.to_thread(
                    backup.restore_backup, settings, box, upload, passphrase=passphrase)
            except backup.RestoreError as exc:
                raise HTTPException(400, str(exc)) from exc
            return {"ok": True, **summary}
        finally:
            upload.unlink(missing_ok=True)
            backups.lock.release()
            manager.release_exclusive()

    @app.get("/api/recovery")
    def recovery_days(days: int = 90, _=Depends(current_user), conn=Depends(get_conn)) -> dict:
        days = max(7, min(days, 3650))
        return {"days": recovery.build(conn, days)}

    @app.get("/api/diagnostics/shapes")
    def diagnostics_shapes(_=Depends(current_user), conn=Depends(get_conn)) -> Response:
        body = _json.dumps(diagnostics.build(conn), indent=1)
        return Response(body, media_type="application/json", headers={
            "Content-Disposition": 'attachment; filename="data-shapes.json"'})

    list_cols = ("id, source, source_id, start_time, sport, name, distance_m, duration_s, "
                 "elevation_gain_m, avg_hr, max_hr, has_samples")

    @app.get("/api/activities")
    def activities(limit: int = 50, offset: int = 0, since: str | None = None,
                   _=Depends(current_user), conn=Depends(get_conn)) -> dict:
        limit = max(1, min(limit, 500))
        where, args = ("WHERE start_time >= ?", [since]) if since else ("", [])
        rows = conn.execute(
            f"SELECT {list_cols} FROM activities {where} "  # noqa: S608
            "ORDER BY start_time DESC LIMIT ? OFFSET ?", (*args, limit, max(0, offset))).fetchall()
        total = conn.execute(f"SELECT COUNT(*) AS n FROM activities {where}", args).fetchone()["n"]  # noqa: S608
        return {"total": total, "items": [dict(r) for r in rows]}

    def get_activity(conn, activity_id: int):
        row = conn.execute("SELECT * FROM activities WHERE id=?", (activity_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Activity not found.")
        return row

    @app.get("/api/activities/{activity_id}")
    def activity_detail(activity_id: int, _=Depends(current_user), conn=Depends(get_conn)) -> dict:
        row = get_activity(conn, activity_id)
        out = {k: row[k] for k in row.keys() if k not in ("summary_json", "file_path")}
        try:
            out["summary"] = _json.loads(row["summary_json"] or "null")
        except ValueError:
            out["summary"] = None
        return out

    @app.get("/api/activities/{activity_id}/samples")
    def activity_samples(activity_id: int, max_points: int = 1500, _=Depends(current_user),
                         conn=Depends(get_conn)) -> dict:
        get_activity(conn, activity_id)
        max_points = max(50, min(max_points, 5000))
        rows = conn.execute(
            "SELECT t, lat, lon, alt, hr, cadence, power, speed, dist FROM samples "
            "WHERE activity_id=? ORDER BY t", (activity_id,)).fetchall()
        total = len(rows)
        if total > max_points:
            stride = -(-total // max_points)
            picked = rows[::stride]
            if picked[-1] is not rows[-1]:
                picked.append(rows[-1])
            rows = picked
        t0 = rows[0]["t"] if rows else 0
        cols = ("lat", "lon", "alt", "hr", "cadence", "power", "speed", "dist")
        data = {"t": [r["t"] - t0 for r in rows], "start_unix": t0, "total_samples": total}
        for c in cols:
            data[c] = [r[c] for r in rows]
        return data

    @app.get("/api/activities/{activity_id}/gpx")
    def activity_gpx(activity_id: int, _=Depends(current_user), conn=Depends(get_conn)) -> Response:
        row = get_activity(conn, activity_id)
        pts = conn.execute(
            "SELECT t, lat, lon, alt, hr, cadence FROM samples WHERE activity_id=? "
            "AND lat IS NOT NULL AND lon IS NOT NULL ORDER BY t", (activity_id,)).fetchall()
        if not pts:
            raise HTTPException(404, "This activity has no GPS track.")
        return Response(
            build_gpx(row["name"] or f"Activity {activity_id}", pts),
            media_type="application/gpx+xml",
            headers={"Content-Disposition": f'attachment; filename="activity-{activity_id}.gpx"'})

    static = settings.static_dir
    if static and (static / "index.html").exists():
        if (static / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise HTTPException(404)
            candidate = (static / path).resolve()
            if path and candidate.is_file() and static.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(static / "index.html", headers={"Cache-Control": "no-cache"})

    return app


def _default_app() -> FastAPI:  # for `uvicorn app.main:app`
    return create_app()


def __getattr__(name: str):
    if name == "app":
        return _default_app()
    raise AttributeError(name)
