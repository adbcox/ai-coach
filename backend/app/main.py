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
from datetime import UTC, date, datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import (
    __version__,
    backup,
    db,
    diagnostics,
    efforts,
    fetch,
    laps,
    maxhr,
    predict,
    recovery,
    references,
    schedule,
    security,
    smb,
    vo2max,
)
from . import (
    body as bodymod,
)
from .config import Settings
from .crypto import SecretBox
from .garmin.client import GarminError
from .gpx import build_gpx
from .library import Library
from .library_routes import make_router
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


SPORT_GROUPS = ["All", "Running", "Cycling", "Hiking", "Other"]
UNIT_OPTIONS = {"distance": ["km", "mi"], "elevation": ["m", "ft"], "weight": ["kg", "lb"], "height": ["cm", "ftin"]}


class Preferences(BaseModel):
    default_sport: str | None = None
    max_hr: int | None = Field(default=None, ge=100, le=230)  # null clears (use automatic)
    birth_year: int | None = Field(default=None, ge=1920, le=2020)
    watch_vo2max: float | None = Field(default=None, ge=15, le=90)
    sex: str | None = None            # "female" | "male"; null clears
    weight_kg: float | None = Field(default=None, ge=25, le=300)  # null clears (use Garmin's)
    height_cm: float | None = Field(default=None, ge=100, le=250)
    birthday: str | None = None       # ISO date YYYY-MM-DD; null clears
    units_distance: str | None = None   # km | mi (also sets pace and speed)
    units_elevation: str | None = None  # m | ft
    units_weight: str | None = None     # kg | lb
    units_height: str | None = None     # cm | ftin


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
    library_transport: Any = None,
    library_resolver: Any = None,
    library_lookups: bool = True,
    library_options: dict | None = None,
) -> FastAPI:
    settings = settings or Settings.from_env()
    db.init_db(settings.db_path)
    box = SecretBox.load(settings.secrets_dir, settings.app_secret)
    # P1: Garmin key is injected as a runtime secret file by the Mini-side
    # launcher (native Infisical CLI only). The DB stores only metadata; the
    # key string lives in process memory for the lifetime of the app.
    runtime_secrets: dict[str, str] = {}
    _conn = db.connect(settings.db_path)
    try:  # a restart kills any running sync; mark it paused so the backfill
          # resumes cleanly (throttle state + downloaded activities are intact).
        _conn.execute(
            "UPDATE sync_runs SET status='paused', finished_at=?, message=COALESCE(message, '') || "
            "' (paused: the server restarted; resumes on next window/tick.)' WHERE status='running'",
            (_now(),))
        _conn.commit()
        if settings.garmin_api_key_file is not None:
            try:
                key_text = settings.garmin_api_key_file.read_text(encoding="utf-8").strip()
            except OSError:
                key_text = ""
            if key_text:
                runtime_secrets[PROVIDER] = key_text
                _conn.execute(
                    "INSERT INTO provider_credentials (provider, secret_enc, updated_at, "
                    "validated_at, credential_source, file_path) VALUES (?, NULL, ?, NULL, 'file', ?) "
                    "ON CONFLICT(provider) DO UPDATE SET secret_enc=NULL, updated_at=excluded.updated_at, "
                    "credential_source='file', file_path=excluded.file_path",
                    (PROVIDER, _now(), str(settings.garmin_api_key_file)),
                )
                _conn.commit()
    finally:
        _conn.close()
    lib = Library(settings.data_dir / "ingest", transport=library_transport,
                  resolver=library_resolver or fetch.system_resolver, lookup_citations=library_lookups,
                  conn_factory=lambda: db.connect(settings.db_path), ocr_langs=os.environ.get("AEC_OCR_LANGS", "eng"),
                  **(library_options or {}))
    lib.ensure_dirs()
    _conn = db.connect(settings.db_path)
    try:
        lib.init_schema(_conn)
        lib.rescan(_conn)
    except Exception:  # a bad file in the library must never stop the app starting
        pass
    finally:
        _conn.close()
    scanner = efforts.EffortScanner(settings)
    manager = SyncManager(settings, box, client_factory, after_sync=scanner.start,
                          runtime_secrets=runtime_secrets)
    failures: dict[str, list[float]] = defaultdict(list)
    backups = backup.BackupManager(settings, box)

    def reindex_library() -> None:
        c = db.connect(settings.db_path)
        try:
            lib.init_schema(c)
            c.execute("DELETE FROM library_items")
            if lib.fts:
                c.execute("DELETE FROM library_fts")
            c.commit()
            lib.rescan(c)
        except Exception:  # never fail a restore because of a bad library file
            pass
        finally:
            c.close()

    def scan_library_inbox() -> None:
        inbox = lib.dir("inbox")
        if inbox.exists() and any(p.is_file() and not p.name.endswith((".part", ".rejected", ".txt")) for p in inbox.iterdir()):
            c = db.connect(settings.db_path)
            try:
                lib.rescan(c)
            finally:
                c.close()

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI):
        task = None
        if start_scheduler:
            scanner.start()  # compute best efforts for any activity that has none yet
            async def loop() -> None:
                while True:
                    await asyncio.sleep(60)
                    try:
                        await asyncio.to_thread(manager.maybe_run_scheduled)
                        await asyncio.to_thread(backups.maybe_run_scheduled)
                        await asyncio.to_thread(scan_library_inbox)
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
    app.state.effort_scanner = scanner
    app.state.backup_manager = backups
    app.state.library = lib

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
        cred = conn.execute(
            "SELECT updated_at, validated_at, credential_source, file_path "
            "FROM provider_credentials WHERE provider=?", (PROVIDER,)).fetchone()
        last = conn.execute("SELECT started_at, finished_at, status, new_activities, message, mode, scheduled "
                            "FROM sync_runs WHERE provider=? ORDER BY id DESC LIMIT 1",
                            (PROVIDER,)).fetchone()
        acts = conn.execute("SELECT COUNT(*) AS n, MIN(start_time) AS first, "
                            "MAX(start_time) AS last FROM activities").fetchone()
        health = {r["kind"]: r["n"] for r in conn.execute(
            "SELECT kind, COUNT(*) AS n FROM wellness_raw WHERE is_empty=0 GROUP BY kind")}
        # P1: a row is "configured" when it carries a usable key reference —
        # either a legacy DB-encrypted blob OR a runtime-secret file path.
        configured = cred is not None and (
            (cred["credential_source"] == "file" and bool(cred["file_path"]))
            or cred["credential_source"] in (None, "db")
        )
        return {
            "stored": {"activities": acts["n"], "first_activity": acts["first"],
                       "last_activity": acts["last"], "health_records": health},
            "schedule": schedule_status(conn),
            "configured": configured,
            "validated_at": cred["validated_at"] if cred else None,
            "credential_source": cred["credential_source"] if cred else None,
            "file_path": cred["file_path"] if cred else None,
            "syncing": manager.running,
            "last_sync": dict(last) if last else None,
        }

    @app.get("/api/providers/garmin")
    def garmin_get(_=Depends(current_user), conn=Depends(get_conn)) -> dict:
        return garmin_status(conn)

    @app.put("/api/providers/garmin")
    def garmin_put(_body: GarminKey, _=Depends(current_user)) -> dict:
        # P1: the Garmin key is provisioned from Infisical by the Mini-side
        # launcher via a runtime secret file; it cannot be set through the UI.
        # Rotate by updating Infisical and re-running coach-start.sh.
        raise HTTPException(
            405,
            "Garmin key is provisioned from Infisical via a runtime secret file; "
            "not settable in-app. Rotate via the Mini-side launcher.",
        )

    @app.delete("/api/providers/garmin")
    def garmin_delete(_=Depends(current_user)) -> dict:
        # P1: same policy — deletion is a launcher/host-side action.
        raise HTTPException(
            405,
            "Garmin key is provisioned from Infisical via a runtime secret file; "
            "not deletable in-app. Rotate via the Mini-side launcher.",
        )

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
            # P1: the restored DB has no provider_credentials row. If the
            # Mini-side launcher provisioned a key file on this host, re-register
            # it so the Garmin panel shows "configured" without a re-login dance.
            if runtime_secrets.get(PROVIDER) and settings.garmin_api_key_file is not None:
                def _reregister() -> None:
                    c = db.connect(settings.db_path)
                    try:
                        c.execute(
                            "INSERT INTO provider_credentials (provider, secret_enc, updated_at, "
                            "validated_at, credential_source, file_path) VALUES (?, NULL, ?, NULL, 'file', ?) "
                            "ON CONFLICT(provider) DO UPDATE SET secret_enc=NULL, "
                            "updated_at=excluded.updated_at, credential_source='file', "
                            "file_path=excluded.file_path",
                            (PROVIDER, _now(), str(settings.garmin_api_key_file)),
                        )
                        c.commit()
                    finally:
                        c.close()
                await asyncio.to_thread(_reregister)
            await asyncio.to_thread(reindex_library)  # the restored database may predate the Library; rebuild its index from the files
            return {"ok": True, **summary}
        finally:
            upload.unlink(missing_ok=True)
            backups.lock.release()
            manager.release_exclusive()

    ZONE_EDGES = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0]  # a common five-zone convention, % of max heart rate (not verified as Garmin's own)

    def read_prefs(conn) -> dict:
        def pref(key: str) -> str | None:
            row = conn.execute("SELECT value FROM sync_state WHERE key=?", (key,)).fetchone()
            return row["value"] if row else None

        sport = pref("pref_default_sport")
        sport = sport if sport in SPORT_GROUPS else "Running"
        custom = pref("pref_max_hr")
        auto = maxhr.estimate(conn)["estimate"] or conn.execute(
            "SELECT MAX(max_hr) AS m FROM activities WHERE max_hr BETWEEN 100 AND 230").fetchone()["m"]
        max_hr = int(custom) if custom else (int(auto) if auto else None)
        zones = ([{"zone": i + 1, "low": round(max_hr * ZONE_EDGES[i]),
                   "high": round(max_hr * ZONE_EDGES[i + 1])} for i in range(5)] if max_hr else [])
        return {"default_sport": sport, "sport_options": SPORT_GROUPS, "max_hr": max_hr,
                "max_hr_source": "custom" if custom else ("auto" if auto else None),
                "max_hr_auto": int(auto) if auto else None, "hr_zones": zones,
                "birth_year": int(pref("pref_birth_year")) if pref("pref_birth_year") else None,
                "watch_vo2max": float(pref("pref_watch_vo2max")) if pref("pref_watch_vo2max") else None,
                **profile_fields(conn, pref),
                "hr_zone_note": "Estimated from max heart rate using a common five-zone convention (50/60/70/80/90%). Your "
                                "Garmin's own boundaries are set from your profile and may differ.",
                "hr_zone_citation": "garmin_zones"}

    def profile_fields(conn, pref) -> dict:
        garmin = bodymod.latest_garmin_weight(conn)
        birthday = pref("pref_birthday")
        custom = float(pref("pref_weight_kg")) if pref("pref_weight_kg") else None
        sex = pref("pref_sex")
        year = int(pref("pref_birth_year")) if pref("pref_birth_year") else None
        return {"sex": sex if sex in ("female", "male") else None,
                "birthday": birthday,
                "age": bodymod.age_from_birthday(birthday) if birthday else bodymod.age_from_birth_year(year),
                "height_cm": float(pref("pref_height_cm")) if pref("pref_height_cm") else None,
                "units": {k: (pref(f"pref_units_{k}") if pref(f"pref_units_{k}") in opts else opts[0])
                          for k, opts in UNIT_OPTIONS.items()},
                "unit_options": UNIT_OPTIONS,
                "weight_kg": custom if custom else (garmin["kg"] if garmin else None),
                "weight_source": "custom" if custom else ("garmin" if garmin else None),
                "weight_garmin_kg": garmin["kg"] if garmin else None,
                "weight_garmin_date": garmin["date"] if garmin else None}

    @app.get("/api/preferences")
    def prefs_get(_=Depends(current_user), conn=Depends(get_conn)) -> dict:
        return read_prefs(conn)

    @app.put("/api/preferences")
    def prefs_put(body_: Preferences, _=Depends(current_user), conn=Depends(get_conn)) -> dict:
        fields = body_.model_fields_set
        if "default_sport" in fields and body_.default_sport is not None:
            if body_.default_sport not in SPORT_GROUPS:
                raise HTTPException(400, f"default_sport must be one of {', '.join(SPORT_GROUPS)}.")
            conn.execute("INSERT INTO sync_state (key, value) VALUES ('pref_default_sport', ?) "
                         "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (body_.default_sport,))
        if "max_hr" in fields:
            if body_.max_hr is None:
                conn.execute("DELETE FROM sync_state WHERE key='pref_max_hr'")
            else:
                conn.execute("INSERT INTO sync_state (key, value) VALUES ('pref_max_hr', ?) "
                             "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(body_.max_hr),))
        for field, key in (("birth_year", "pref_birth_year"), ("watch_vo2max", "pref_watch_vo2max")):
            if field in fields:
                value = getattr(body_, field)
                if value is None:
                    conn.execute("DELETE FROM sync_state WHERE key=?", (key,))
                else:
                    conn.execute("INSERT INTO sync_state (key, value) VALUES (?, ?) "
                                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
                if field == "watch_vo2max" and value is not None:
                    conn.execute("INSERT INTO sync_state (key, value) VALUES ('pref_watch_vo2max_date', ?) "
                                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (_now()[:10],))
        if "sex" in fields:
            if body_.sex is None:
                conn.execute("DELETE FROM sync_state WHERE key='pref_sex'")
            elif body_.sex in ("female", "male"):
                conn.execute("INSERT INTO sync_state (key, value) VALUES ('pref_sex', ?) "
                             "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (body_.sex,))
            else:
                raise HTTPException(400, "sex must be female or male (the value physiology formulas use), or blank.")
        if "birthday" in fields:
            if body_.birthday is None or body_.birthday == "":
                conn.execute("DELETE FROM sync_state WHERE key IN ('pref_birthday','pref_birth_year')")
            else:
                try:
                    bd = date.fromisoformat(body_.birthday)
                except ValueError:
                    raise HTTPException(400, "Enter your birthday as a date.") from None
                if not (date(1920, 1, 1) <= bd < date.today()):
                    raise HTTPException(400, "That birthday is outside a plausible range.")
                for k, v in (("pref_birthday", bd.isoformat()), ("pref_birth_year", str(bd.year))):
                    conn.execute("INSERT INTO sync_state (key, value) VALUES (?, ?) "
                                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (k, v))
        if "height_cm" in fields:
            if body_.height_cm is None:
                conn.execute("DELETE FROM sync_state WHERE key='pref_height_cm'")
            else:
                conn.execute("INSERT INTO sync_state (key, value) VALUES ('pref_height_cm', ?) "
                             "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(round(body_.height_cm, 1)),))
        for unit_key, opts in UNIT_OPTIONS.items():
            chosen = getattr(body_, f"units_{unit_key}")
            if f"units_{unit_key}" in fields and chosen is not None:
                if chosen not in opts:
                    raise HTTPException(400, f"{unit_key} units must be one of {', '.join(opts)}.")
                conn.execute("INSERT INTO sync_state (key, value) VALUES (?, ?) "
                             "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (f"pref_units_{unit_key}", chosen))
        if "weight_kg" in fields:
            if body_.weight_kg is None:
                conn.execute("DELETE FROM sync_state WHERE key='pref_weight_kg'")
            else:
                conn.execute("INSERT INTO sync_state (key, value) VALUES ('pref_weight_kg', ?) "
                             "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(body_.weight_kg),))
        conn.commit()
        return read_prefs(conn)

    @app.get("/api/weight")
    def weight_get(_=Depends(current_user), conn=Depends(get_conn)) -> dict:
        return {"history": bodymod.weight_history(conn)[-365:]}

    app.include_router(make_router(lib, get_conn, current_user))

    @app.get("/api/references")
    def references_list(_=Depends(current_user), conn=Depends(get_conn)) -> dict:
        copies = lib.copies_by_ref(conn)
        return {"verified_levels": references.VERIFIED,
                "references": [{**r, "your_copy": copies.get(r["id"])} for r in references.all_references()]}

    @app.get("/api/maxhr")
    def maxhr_get(_=Depends(current_user), conn=Depends(get_conn)) -> dict:
        return maxhr.estimate(conn) | {"scan_pending": len(efforts.pending(conn))}

    @app.post("/api/maxhr/apply")
    def maxhr_apply(_=Depends(current_user), conn=Depends(get_conn)) -> dict:
        est = maxhr.estimate(conn)["estimate"]
        if not est:
            raise HTTPException(400, "There is not enough heart-rate data to estimate a maximum yet.")
        conn.execute("INSERT INTO sync_state (key, value) VALUES ('pref_max_hr', ?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(est),))
        conn.commit()
        return read_prefs(conn)

    @app.get("/api/vo2max")
    def vo2max_get(_=Depends(current_user), conn=Depends(get_conn)) -> dict:
        return vo2max.build(conn)

    @app.post("/api/activities/{activity_id}/race")
    def race_mark(activity_id: int, _=Depends(current_user), conn=Depends(get_conn)) -> dict:
        get_activity(conn, activity_id)
        conn.execute("INSERT OR IGNORE INTO race_marks (activity_id, marked_at) VALUES (?, ?)", (activity_id, _now()))
        conn.commit()
        return {"is_race": True}

    @app.delete("/api/activities/{activity_id}/race")
    def race_unmark(activity_id: int, _=Depends(current_user), conn=Depends(get_conn)) -> dict:
        conn.execute("DELETE FROM race_marks WHERE activity_id=?", (activity_id,))
        conn.commit()
        return {"is_race": False}

    @app.get("/api/predictions")
    def predictions(window_days: int = 365, include_indoor: bool = True, include_trail: bool = True,
                    use_gap: bool = True, _=Depends(current_user), conn=Depends(get_conn)) -> dict:
        window_days = max(30, min(window_days, 1825))
        result = predict.build(conn, window_days, include_indoor, include_trail, use_gap)
        result["scan"] = {"running": scanner.running, "done": scanner.done, "total": scanner.total,
                          "pending": len(efforts.pending(conn))}
        return result

    @app.post("/api/efforts/{activity_id}/exclude")
    def effort_exclude(activity_id: int, _=Depends(current_user), conn=Depends(get_conn)) -> dict:
        get_activity(conn, activity_id)
        conn.execute("INSERT OR IGNORE INTO effort_exclusions (activity_id, created_at) VALUES (?, ?)",
                     (activity_id, _now()))
        conn.commit()
        return {"excluded": True}

    @app.delete("/api/efforts/{activity_id}/exclude")
    def effort_include(activity_id: int, _=Depends(current_user), conn=Depends(get_conn)) -> dict:
        conn.execute("DELETE FROM effort_exclusions WHERE activity_id=?", (activity_id,))
        conn.commit()
        return {"excluded": False}

    @app.post("/api/efforts/rescan", status_code=202)
    def efforts_rescan(_=Depends(current_user), conn=Depends(get_conn)) -> dict:
        conn.execute("DELETE FROM effort_scan")
        conn.commit()
        return {"started": scanner.start()}

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
        out["is_race"] = conn.execute("SELECT 1 FROM race_marks WHERE activity_id=?", (activity_id,)).fetchone() is not None
        return out

    @app.get("/api/activities/{activity_id}/laps")
    def activity_laps(activity_id: int, _=Depends(current_user), conn=Depends(get_conn)) -> dict:
        row = get_activity(conn, activity_id)
        if conn.execute("SELECT 1 FROM lap_scan WHERE activity_id=? AND version=?", (activity_id, laps.LAP_VERSION)).fetchone() is None:
            laps.scan_one(conn, settings, row["id"])  # one FIT file: quick, and means the page never has to wait for the background pass
        return laps.get_laps(conn, activity_id)

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
