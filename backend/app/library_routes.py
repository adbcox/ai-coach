"""HTTP routes for the Library (see library.py). All of them need a signed-in user."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import references
from .library import (
    ACTIONABLE_TEMPLATE,
    EVIDENCE_TYPES,
    MAX_UPLOAD,
    STATUSES,
    Library,
    LibraryError,
)


class LinkBody(BaseModel):
    url: str = Field(min_length=3, max_length=2000)
    ref_id: str | None = None


class CitationBody(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    authors: str | list[str] | None = None
    year: int | None = Field(default=None, ge=1800, le=2100)
    venue: str | None = Field(default=None, max_length=300)
    doi: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=5000)
    evidence_type: str | None = None
    ref_id: str | None = None


class ActionableBody(BaseModel):
    body: str = Field(max_length=200_000)
    status: str = "draft"


def make_router(lib: Library, get_conn, current_user) -> APIRouter:
    r = APIRouter(prefix="/api/library", dependencies=[Depends(current_user)])

    def guard(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except LibraryError as e:
            raise HTTPException(400, str(e)) from e

    def known_ref(ref_id: str | None) -> str | None:
        if ref_id and ref_id not in {x["id"] for x in references.all_references()}:
            raise HTTPException(400, "Unknown source id.")
        return ref_id or None

    async def body_bytes(request: Request) -> bytes:
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > MAX_UPLOAD:
            raise HTTPException(413, f"That file is larger than {MAX_UPLOAD // (1024 * 1024)} MB.")
        data = await request.body()
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, f"That file is larger than {MAX_UPLOAD // (1024 * 1024)} MB.")
        return data

    @r.get("")
    def list_items(q: str = "", tag: str = "", status: str = "", reviewed: str = "", conn=Depends(get_conn)) -> dict[str, Any]:
        items = lib.list(conn, q=q, tag=tag, status=status, reviewed=reviewed)
        counts = {s: conn.execute("SELECT COUNT(*) n FROM library_items WHERE status=?", (s,)).fetchone()["n"] for s in STATUSES}
        total = conn.execute("SELECT COUNT(*) n FROM library_items").fetchone()["n"]
        inbox = lib.dir("inbox")
        waiting = len([p for p in inbox.iterdir() if p.is_file() and not p.name.endswith((".part", ".rejected", ".txt"))]) \
            if inbox.exists() else 0
        return {"items": items, "tags": lib.all_tags(conn), "counts": counts, "total": total, "inbox_waiting": waiting,
                "statuses": list(STATUSES), "evidence_types": EVIDENCE_TYPES, "template": ACTIONABLE_TEMPLATE,
                "search": bool(q), "folder": "ingest"}

    @r.post("/rescan")
    def rescan(conn=Depends(get_conn)) -> dict[str, Any]:
        return lib.rescan(conn)

    @r.put("/upload")
    async def upload(request: Request, filename: str, ref_id: str | None = None, conn=Depends(get_conn)) -> dict[str, Any]:
        data = await body_bytes(request)
        ref = known_ref(ref_id)
        return await run_in_threadpool(guard, lib.ingest_bytes, filename[:200], data, ref_id=ref, conn=conn)

    @r.post("/link")
    def link(body: LinkBody, conn=Depends(get_conn)) -> dict[str, Any]:
        return guard(lib.ingest_url, body.url, conn=conn, ref_id=known_ref(body.ref_id))

    @r.post("/citation")
    def citation(body: CitationBody, conn=Depends(get_conn)) -> dict[str, Any]:
        d = body.model_dump()
        d["ref_id"] = known_ref(d.get("ref_id"))
        return guard(lib.add_citation, d, conn=conn)

    @r.get("/{item_id}")
    def get_item(item_id: str) -> dict[str, Any]:
        try:
            return lib.get(item_id)
        except LibraryError as e:
            raise HTTPException(404, str(e)) from e

    @r.patch("/{item_id}")
    def patch_item(item_id: str, patch: dict[str, Any], conn=Depends(get_conn)) -> dict[str, Any]:
        if "ref_id" in patch:
            patch["ref_id"] = known_ref(patch["ref_id"] or None)
        return guard(lib.update, item_id, patch, conn=conn)

    @r.put("/{item_id}/actionable")
    def put_actionable(item_id: str, body: ActionableBody, conn=Depends(get_conn)) -> dict[str, Any]:
        return guard(lib.write_actionable, item_id, body.body, body.status, conn=conn)

    @r.post("/{item_id}/attach")
    async def attach(item_id: str, request: Request, filename: str, conn=Depends(get_conn)) -> dict[str, Any]:
        data = await body_bytes(request)
        return await run_in_threadpool(guard, lib.attach_file, item_id, filename[:200], data, conn=conn)

    @r.post("/{item_id}/ocr")
    def read_scan(item_id: str, conn=Depends(get_conn)) -> dict[str, Any]:
        return guard(lib.retry_ocr, item_id, conn=conn)

    @r.post("/{item_id}/reconvert")
    def reconvert(item_id: str, conn=Depends(get_conn)) -> dict[str, Any]:
        return guard(lib.reconvert, item_id, conn=conn)

    @r.get("/{item_id}/source")
    def source(item_id: str):
        try:
            lib._valid_id(item_id)
        except LibraryError as e:
            raise HTTPException(404, str(e)) from e
        files = lib.source_files(item_id)
        if not files:
            raise HTTPException(404, "There is no original file for this item.")
        p = files[0]
        media = {".pdf": "application/pdf", ".html": "text/plain; charset=utf-8", ".md": "text/markdown; charset=utf-8",
                 ".txt": "text/plain; charset=utf-8"}.get(p.suffix.lower(), "application/octet-stream")
        return FileResponse(p, media_type=media, filename=p.name, headers={"X-Content-Type-Options": "nosniff"})

    @r.delete("/{item_id}")
    def delete_item(item_id: str, conn=Depends(get_conn)) -> dict[str, bool]:
        guard(lib.delete, item_id, conn=conn)
        return {"ok": True}

    return r
