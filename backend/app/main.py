"""FastAPI application: auth, Garmin key settings, sync, activities, static SPA."""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__, db, security
from .config import Settings
from .crypto import SecretBox
from .garmin.client import GarminError
from .sync import PROVIDER, ClientFactory, SyncManager, default_client_factory

COOKIE = "aec_session"
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "aec"
_MAX_FAILS, _WINDOW_S = 5, 300


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=256)


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
    manager = SyncManager(settings, box, client_factory)
    failures: dict[str, list[float]] = defaultdict(list)

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI):
        task = None
        if start_scheduler and settings.sync_interval_hours > 0:
            async def loop() -> None:
                while True:
                    await asyncio.sleep(settings.sync_interval_hours * 3600)
                    await asyncio.to_thread(manager.run_once)
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

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

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

    def garmin_status(conn) -> dict:
        cred = conn.execute("SELECT updated_at, validated_at FROM provider_credentials "
                            "WHERE provider=?", (PROVIDER,)).fetchone()
        last = conn.execute("SELECT started_at, finished_at, status, new_activities, message "
                            "FROM sync_runs WHERE provider=? ORDER BY id DESC LIMIT 1",
                            (PROVIDER,)).fetchone()
        acts = conn.execute("SELECT COUNT(*) AS n, MIN(start_time) AS first, "
                            "MAX(start_time) AS last FROM activities").fetchone()
        health = {r["kind"]: r["n"] for r in conn.execute(
            "SELECT kind, COUNT(*) AS n FROM wellness_raw WHERE is_empty=0 GROUP BY kind")}
        return {
            "stored": {"activities": acts["n"], "first_activity": acts["first"],
                       "last_activity": acts["last"], "health_records": health},
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

    @app.post("/api/sync", status_code=202)
    def sync_start(full: bool = False, _=Depends(current_user), conn=Depends(get_conn)) -> dict:
        if conn.execute("SELECT 1 FROM provider_credentials WHERE provider=?",
                        (PROVIDER,)).fetchone() is None:
            raise HTTPException(400, "Add your Garmin key in Settings first.")
        if not manager.start_background(full=full):
            raise HTTPException(409, "A sync is already running.")
        return {"started": True}

    @app.get("/api/activities")
    def activities(limit: int = 50, offset: int = 0, _=Depends(current_user),
                   conn=Depends(get_conn)) -> dict:
        limit = max(1, min(limit, 200))
        rows = conn.execute(
            "SELECT id, source, source_id, start_time, sport, name, distance_m, duration_s, "
            "elevation_gain_m, avg_hr, max_hr, has_samples FROM activities "
            "ORDER BY start_time DESC LIMIT ? OFFSET ?", (limit, max(0, offset))).fetchall()
        total = conn.execute("SELECT COUNT(*) AS n FROM activities").fetchone()["n"]
        return {"total": total, "items": [dict(r) for r in rows]}

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
