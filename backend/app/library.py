"""The Library: your own sources, kept as Markdown files you can read in the app and on disk.

Layout (inside the data volume, never in git or the image; see docs/ingest.md):

    ingest/3-source/<id>.<ext>      the original file, untouched
    ingest/2-fulltext/<id>.md       conversion to Markdown, with a front-matter header (the source of truth)
    ingest/1-actionable/<id>.md     your own short notes on what changes training decisions (optional)
    ingest/inbox/                   drop files here; they are converted on the next scan
    ingest/INDEX.md                 a readable list linking all three versions of every source

The files are the source of truth. The database holds only a search index that can be rebuilt from them.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import threading
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from . import convert, fetch

TIERS = ("1-actionable", "2-fulltext", "3-source", "inbox")
STATUSES = ("converted", "citation_only", "needs_ocr", "failed")
EVIDENCE_TYPES = ["RCT", "meta-analysis", "systematic review", "review", "observational", "laboratory study",
                  "guideline", "coach opinion", "book", "other"]
EDITABLE = ("title", "authors", "year", "venue", "doi", "url", "ref_id", "evidence_type", "reviewed", "tags", "notes")
KEY_ORDER = ["id", "title", "authors", "year", "venue", "doi", "url", "ref_id", "added", "source", "sha256",
             "converter", "pages", "words", "status", "message", "evidence_type", "reviewed", "tags", "notes"]
MAX_UPLOAD = 80 * 1024 * 1024

ACTIONABLE_TEMPLATE = """## Items
1. **Claim/action:**
   - **Applies to:** (population, level, volume, conditions)
   - **Size/strength:** (effect size or "no numbers given"; how confident)
   - **Where:** (page or section of the full text, with a short quote)
   - **Caveats:** (what would make this wrong or not apply to you)

## Conflicts with other sources
none known

## Omitted
(what you left out: methods, background, tangents)
"""


class LibraryError(Exception):
    """A problem with a request that is safe to show to the user."""


# ---------------------------------------------------------------- front matter -------------------------------------

def dump_front_matter(meta: dict[str, Any], order: list[str] | None = None) -> str:
    keys = [k for k in (order or KEY_ORDER) if k in meta] + [k for k in meta if k not in (order or KEY_ORDER)]
    lines = ["---"]
    for k in keys:
        v = meta[k]
        if v is None or v == "" or v == []:
            continue
        lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")  # JSON scalars and lists are valid YAML
    lines.append("---")
    return "\n".join(lines) + "\n"


def _scalar(raw: str) -> Any:
    raw = raw.strip()
    if not raw or raw in ("~", "null"):
        return None
    if raw[0] in "\"[{" or raw in ("true", "false") or re.fullmatch(r"-?\d+(\.\d+)?", raw):
        try:
            return json.loads(raw)
        except ValueError:
            if raw[0] == "[" and raw[-1] == "]":  # hand-written YAML list: [a, b]
                return [x.strip().strip("'\"") for x in raw[1:-1].split(",") if x.strip()]
    if raw[0] == "'" and raw[-1] == "'" and len(raw) > 1:
        return raw[1:-1].replace("''", "'")
    return raw


def parse_front_matter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---"):
        return {}, text
    end = re.search(r"^---\s*$", text[3:], re.M)
    if not end:
        return {}, text
    head, body = text[3:3 + end.start()], text[3 + end.end():]
    meta: dict[str, Any] = {}
    key = None
    for line in head.splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            key = m.group(1)
            meta[key] = _scalar(m.group(2))
        elif key and line.strip().startswith("- "):  # block-style list written by hand
            if not isinstance(meta.get(key), list):
                meta[key] = []
            meta[key].append(_scalar(line.strip()[2:]))
    return meta, body.lstrip("\n")


# ------------------------------------------------------------------ helpers ---------------------------------------

def slugify(text: str, limit: int = 60) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower().encode("ascii", "ignore").decode()).strip("-")
    return s[:limit].strip("-")


_STOP = {"the", "a", "an", "of", "and", "in", "on", "for", "to", "with", "by", "from", "at", "is", "are"}


def make_base_id(meta: dict[str, Any], filename: str = "") -> str:
    title_words = [w for w in re.findall(r"[a-z0-9]+", (meta.get("title") or "").lower()) if w not in _STOP][:4]
    surname = ""
    if meta.get("authors"):
        name = str(meta["authors"][0]).strip()
        tokens = [x for x in re.split(r"[ ,.]+", name) if x]
        if "," in name:
            surname = slugify(name.split(",")[0], 20)
        elif len(tokens) > 1 and re.fullmatch(r"[A-Z]{1,3}", tokens[-1]):  # "Daniels J": surname first, then initials
            surname = slugify(tokens[0], 20)
        elif tokens:
            surname = slugify(tokens[-1], 20)
    parts = [p for p in (surname, str(meta.get("year") or ""), "-".join(title_words)) if p]
    base = slugify("-".join(parts), 70)
    return base or slugify(Path(filename).stem, 60) or "source"


def _atomic_write(path: Path, data: bytes | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    tmp.replace(path)


# ------------------------------------------------------------------ the library -----------------------------------

class Library:
    def __init__(self, root: Path, *, transport: httpx.BaseTransport | None = None,
                 resolver: fetch.Resolver = fetch.system_resolver, lookup_citations: bool = True) -> None:
        self.root = Path(root)
        self.transport = transport
        self.resolver = resolver
        self.lookup_citations = lookup_citations
        self.lock = threading.RLock()
        self.fts = True

    # -- paths
    def dir(self, tier: str) -> Path:
        return self.root / tier

    def ensure_dirs(self) -> None:
        for t in TIERS:
            self.dir(t).mkdir(parents=True, exist_ok=True)

    def ft_path(self, item_id: str) -> Path:
        return self.dir("2-fulltext") / f"{item_id}.md"

    def act_path(self, item_id: str) -> Path:
        return self.dir("1-actionable") / f"{item_id}.md"

    def source_files(self, item_id: str) -> list[Path]:
        d = self.dir("3-source")
        return sorted(p for p in d.glob(f"{item_id}.*") if p.is_file()) if d.exists() else []

    def _valid_id(self, item_id: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,120}", item_id or ""):
            raise LibraryError("Unknown item.")
        return item_id

    def unique_id(self, base: str) -> str:
        i, cand = 1, base
        while self.ft_path(cand).exists() or self.source_files(cand):
            i += 1
            cand = f"{base}-{i}"
        return cand

    # -- schema and index
    def init_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute("""CREATE TABLE IF NOT EXISTS library_items (
            id TEXT PRIMARY KEY, title TEXT, authors TEXT, year INTEGER, venue TEXT, doi TEXT, url TEXT, ref_id TEXT,
            status TEXT, reviewed INTEGER DEFAULT 0, evidence_type TEXT, tags TEXT, words INTEGER, pages INTEGER,
            added TEXT, source TEXT, message TEXT, converter TEXT, notes_status TEXT, mtime REAL, act_mtime REAL)""")
        try:
            conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS library_fts USING fts5("
                         "id UNINDEXED, title, authors, tags, notes, body, tokenize='porter unicode61')")
            self.fts = True
        except sqlite3.OperationalError:
            self.fts = False
        conn.commit()

    def index_item(self, conn: sqlite3.Connection, item_id: str) -> None:
        path = self.ft_path(item_id)
        if not path.exists():
            conn.execute("DELETE FROM library_items WHERE id=?", (item_id,))
            if self.fts:
                conn.execute("DELETE FROM library_fts WHERE id=?", (item_id,))
            return
        meta, body = parse_front_matter(path.read_text("utf-8", errors="replace"))
        act = self.read_actionable(item_id)
        notes_text = " ".join(x for x in (str(meta.get("notes") or ""), act["body"] if act["exists"] else "") if x)
        row = (item_id, meta.get("title") or item_id, " ; ".join(meta.get("authors") or []), _int(meta.get("year")),
               meta.get("venue"), meta.get("doi"), meta.get("url"), meta.get("ref_id"), meta.get("status") or "converted",
               1 if meta.get("reviewed") else 0, meta.get("evidence_type"), json.dumps(meta.get("tags") or [], ensure_ascii=False),
               (_int(meta.get("words")) if _int(meta.get("words")) is not None else convert.word_count(body)), _int(meta.get("pages")), meta.get("added"),
               meta.get("source"), meta.get("message"), meta.get("converter"),
               (act["status"] if act["exists"] else None), path.stat().st_mtime,
               self.act_path(item_id).stat().st_mtime if act["exists"] else None)
        conn.execute("INSERT OR REPLACE INTO library_items (id,title,authors,year,venue,doi,url,ref_id,status,reviewed,"
                     "evidence_type,tags,words,pages,added,source,message,converter,notes_status,mtime,act_mtime) "
                     "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", row)
        if self.fts:
            conn.execute("DELETE FROM library_fts WHERE id=?", (item_id,))
            conn.execute("INSERT INTO library_fts (id,title,authors,tags,notes,body) VALUES (?,?,?,?,?,?)",
                         (item_id, row[1], row[2], " ".join(meta.get("tags") or []), notes_text, body[:3_000_000]))

    def rescan(self, conn: sqlite3.Connection) -> dict[str, int]:
        """Bring the index in line with the files; convert anything dropped in inbox/ or left without a conversion."""
        self.ensure_dirs()
        with self.lock:
            made = self.process_inbox(conn)
            seen = set()
            changed = 0
            known = {r["id"]: r for r in conn.execute("SELECT id, mtime, act_mtime FROM library_items")}
            for p in sorted(self.dir("2-fulltext").glob("*.md")):
                item_id = p.stem
                if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,120}", item_id):
                    continue
                seen.add(item_id)
                ap = self.act_path(item_id)
                r = known.get(item_id)
                if r and r["mtime"] == p.stat().st_mtime and (r["act_mtime"] or None) == (ap.stat().st_mtime if ap.exists() else None):
                    continue
                self._ensure_front_matter(item_id)
                self.index_item(conn, item_id)
                changed += 1
            for item_id in set(known) - seen:
                self.index_item(conn, item_id)
                changed += 1
            self.write_index_md(conn)
            conn.commit()
            return {"converted": made, "reindexed": changed}

    def _ensure_front_matter(self, item_id: str) -> None:
        """A Markdown file you dropped into 2-fulltext/ by hand gets a header so the app can track it."""
        p = self.ft_path(item_id)
        text = p.read_text("utf-8", errors="replace")
        meta, body = parse_front_matter(text)
        if meta.get("id") == item_id and meta.get("added"):
            return
        c = convert.text_to_markdown(body.encode("utf-8"), markdown=True)
        meta.setdefault("id", item_id)
        meta.setdefault("title", c.title or item_id)
        meta.setdefault("added", date.today().isoformat())
        meta.setdefault("status", "converted")
        meta.setdefault("words", convert.word_count(body))
        meta.setdefault("converter", "written or dropped in by hand")
        if c.doi:
            meta.setdefault("doi", c.doi)
        _atomic_write(p, dump_front_matter(meta) + "\n" + body)

    def process_inbox(self, conn: sqlite3.Connection) -> int:
        """Convert files dropped into inbox/ (they are moved into 3-source/ and converted)."""
        n = 0
        inbox = self.dir("inbox")
        if inbox.exists():
            for p in sorted(inbox.iterdir()):
                if not p.is_file() or p.name.startswith(".") or p.name.endswith(".part"):
                    continue
                try:
                    data = p.read_bytes()
                    self.ingest_bytes(p.name, data, conn=conn)
                    p.unlink()
                    n += 1
                except LibraryError as e:
                    (inbox / (p.name + ".error.txt")).write_text(str(e), "utf-8")
                    p.rename(inbox / (p.name + ".rejected"))
        # originals in 3-source/ with no conversion yet (e.g. copied there by hand)
        src = self.dir("3-source")
        if src.exists():
            for p in sorted(src.iterdir()):
                if p.is_file() and not p.name.startswith(".") and not self.ft_path(p.stem).exists() \
                        and re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,120}", p.stem):
                    try:
                        self._write_conversion(p.stem, p.name, p.read_bytes(), source_name=p.name)
                        n += 1
                    except LibraryError:
                        continue
        return n

    # -- reading
    def get(self, item_id: str, *, with_body: bool = True) -> dict[str, Any]:
        self._valid_id(item_id)
        p = self.ft_path(item_id)
        if not p.exists():
            raise LibraryError("Unknown item.")
        meta, body = parse_front_matter(p.read_text("utf-8", errors="replace"))
        meta["id"] = item_id
        meta.setdefault("status", "converted")
        meta.setdefault("tags", [])
        meta.setdefault("authors", [])
        out = {**meta, "has_source": bool(self.source_files(item_id)),
               "source_ext": self.source_files(item_id)[0].suffix if self.source_files(item_id) else None,
               "actionable": self.read_actionable(item_id)}
        if with_body:
            out["fulltext"] = body
        return out

    def read_actionable(self, item_id: str) -> dict[str, Any]:
        p = self.act_path(item_id)
        if not p.exists():
            return {"exists": False, "status": None, "body": "", "reviewed_on": None}
        meta, body = parse_front_matter(p.read_text("utf-8", errors="replace"))
        return {"exists": True, "status": meta.get("status") or "draft", "body": body, "reviewed_on": meta.get("reviewed_on")}

    # -- writing
    def _unique_by_hash(self, conn: sqlite3.Connection | None, sha: str, doi: str | None) -> dict[str, Any] | None:
        for p in self.dir("2-fulltext").glob("*.md"):
            head = p.read_text("utf-8", errors="replace")[:4000]
            meta, _ = parse_front_matter(head + "\n---\n") if head.startswith("---") else ({}, "")
            if meta.get("sha256") == sha or (doi and meta.get("doi") == doi and meta.get("status") != "citation_only"):
                return self.get(p.stem, with_body=False)
        return None

    def _fill_from_crossref(self, c: convert.Converted) -> None:
        if not (self.lookup_citations and c.doi):
            return
        rec = fetch.crossref_record(c.doi, transport=self.transport)
        if rec:
            c.title = rec["title"] or c.title
            c.authors = rec["authors"] or c.authors
            c.year = rec["year"] or c.year
            c.venue = rec["venue"] or c.venue
            c.doi = rec["doi"]
            c.url = c.url or rec["url"]

    def _write_conversion(self, item_id: str, filename: str, data: bytes, *, source_name: str | None = None,
                          ref_id: str | None = None, url: str | None = None,
                          keep: dict[str, Any] | None = None, c: convert.Converted | None = None) -> dict[str, Any]:
        """Convert `data` and write 2-fulltext (and 3-source unless it is already there)."""
        ext = ""
        filled_here = c is None
        if c is None:
            c, ext = convert.convert(filename, data)
            if not ext:
                raise LibraryError(c.message)
        else:
            ext = Path(source_name or filename).suffix
        if filled_here:
            self._fill_from_crossref(c)
        meta: dict[str, Any] = {
            "id": item_id, "title": c.title or Path(filename).stem, "authors": c.authors, "year": c.year, "venue": c.venue,
            "doi": c.doi, "url": url or c.url, "ref_id": ref_id, "added": date.today().isoformat(),
            "source": f"3-source/{source_name or (item_id + ext)}", "sha256": hashlib.sha256(data).hexdigest(),
            "converter": c.converter, "pages": c.pages, "words": convert.word_count(c.markdown), "status": c.status,
            "message": c.message or None, "reviewed": False, "tags": [],
        }
        if keep:
            meta.update({k: v for k, v in keep.items() if v not in (None, "", [])})
            meta["id"] = item_id
        if source_name is None:
            _atomic_write(self.dir("3-source") / f"{item_id}{ext}", data)
        body = c.markdown if c.markdown else (f"*{c.message}*\n" if c.message else "")
        _atomic_write(self.ft_path(item_id), dump_front_matter(meta) + "\n" + body + ("\n" if body and not body.endswith("\n") else ""))
        return meta

    def ingest_bytes(self, filename: str, data: bytes, *, ref_id: str | None = None, url: str | None = None,
                     conn: sqlite3.Connection | None = None, conv: convert.Converted | None = None) -> dict[str, Any]:
        if not data:
            raise LibraryError("The file is empty.")
        if len(data) > MAX_UPLOAD:
            raise LibraryError(f"That file is larger than {MAX_UPLOAD // (1024 * 1024)} MB.")
        self.ensure_dirs()
        with self.lock:
            sha = hashlib.sha256(data).hexdigest()
            c, ext = (conv, "") if conv is not None else convert.convert(filename, data)
            if conv is None and not ext:
                raise LibraryError(c.message)
            dup = self._unique_by_hash(conn, sha, c.doi)
            if dup:
                return {**dup, "duplicate": True}
            self._fill_from_crossref(c)
            item_id = self.unique_id(make_base_id({"title": c.title, "authors": c.authors, "year": c.year}, filename))
            real_ext = ext or Path(filename).suffix or ".html"
            _atomic_write(self.dir("3-source") / f"{item_id}{real_ext}", data)
            meta = self._write_conversion(item_id, filename, data, source_name=f"{item_id}{real_ext}", ref_id=ref_id,
                                          url=url, c=c)
            if conn is not None:
                self.index_item(conn, item_id)
                self.write_index_md(conn)
                conn.commit()
            return {**meta, "duplicate": False}

    def ingest_url(self, url: str, *, conn: sqlite3.Connection, ref_id: str | None = None) -> dict[str, Any]:
        raw = url.strip()
        doi = convert.find_doi(raw) if re.search(r"doi\.org/|^10\.\d{4,9}/|^doi:", raw, re.I) else None
        if doi:
            return self.add_doi(doi, conn=conn, ref_id=ref_id)
        try:
            body, ctype, final = fetch.fetch(raw, transport=self.transport, resolve=self.resolver)
        except fetch.FetchError as e:
            raise LibraryError(str(e)) from e
        is_pdf = body[:5] == b"%PDF-" or ctype == "application/pdf"
        if is_pdf:
            name = (Path(final.split("?")[0]).name or "download") + ("" if final.lower().split("?")[0].endswith(".pdf") else ".pdf")
            return self.ingest_bytes(name, body, ref_id=ref_id, url=final, conn=conn)
        if ctype and "html" not in ctype and "xml" not in ctype and "text" not in ctype:
            raise LibraryError(f"That address is a {ctype} file, which is not supported.")
        html = body.decode("utf-8", "replace")
        c = convert.html_to_markdown(html, final)
        if c.status == "failed":
            raise LibraryError(c.message)
        return self.ingest_bytes("page.html", body, ref_id=ref_id, url=final, conn=conn, conv=c)

    def add_doi(self, doi: str, *, conn: sqlite3.Connection, ref_id: str | None = None) -> dict[str, Any]:
        doi = convert.clean_doi(doi)
        rec = fetch.crossref_record(doi, transport=self.transport) if self.lookup_citations else None
        if not rec:
            raise LibraryError("Could not look up that DOI right now. Use “Type a citation” instead.")
        return self.add_citation({**rec, "ref_id": ref_id, "url": rec.get("url") or f"https://doi.org/{doi}"}, conn=conn)

    def add_citation(self, fields: dict[str, Any], *, conn: sqlite3.Connection) -> dict[str, Any]:
        title = str(fields.get("title") or "").strip()
        if not title:
            raise LibraryError("A title is required.")
        authors = fields.get("authors") or []
        if isinstance(authors, str):
            authors = [a.strip() for a in re.split(r";|\n", authors) if a.strip()]
        year = _int(fields.get("year"))
        doi = convert.clean_doi(fields["doi"]) if fields.get("doi") else None
        self.ensure_dirs()
        with self.lock:
            for p in self.dir("2-fulltext").glob("*.md"):
                m, _ = parse_front_matter(p.read_text("utf-8", errors="replace")[:4000] + "\n---\n")
                if doi and m.get("doi") == doi:
                    return {**self.get(p.stem, with_body=False), "duplicate": True}
            item_id = self.unique_id(make_base_id({"title": title, "authors": authors, "year": year}, title))
            meta = {"id": item_id, "title": title, "authors": authors, "year": year, "venue": fields.get("venue") or None,
                    "doi": doi, "url": fields.get("url") or None, "ref_id": fields.get("ref_id") or None,
                    "added": date.today().isoformat(), "status": "citation_only", "words": 0, "reviewed": False, "tags": [],
                    "converter": "typed in", "evidence_type": fields.get("evidence_type") or None,
                    "notes": fields.get("notes") or None}
            _atomic_write(self.ft_path(item_id), dump_front_matter(meta) +
                          "\n*Citation only: no full text has been attached. Upload the PDF to add it.*\n")
            self.index_item(conn, item_id)
            self.write_index_md(conn)
            conn.commit()
            return {**meta, "duplicate": False}

    def attach_file(self, item_id: str, filename: str, data: bytes, *, conn: sqlite3.Connection) -> dict[str, Any]:
        """Add the full text to an item that so far has only a citation."""
        self._valid_id(item_id)
        with self.lock:
            cur = self.get(item_id, with_body=False)
            c, ext = convert.convert(filename, data)
            if not ext:
                raise LibraryError(c.message)
            keep = {k: cur.get(k) for k in ("title", "authors", "year", "venue", "doi", "url", "ref_id", "evidence_type",
                                            "reviewed", "tags", "notes", "added")}
            for old in self.source_files(item_id):
                old.unlink()
            _atomic_write(self.dir("3-source") / f"{item_id}{ext}", data)
            self._write_conversion(item_id, filename, data, source_name=f"{item_id}{ext}", keep=keep, c=c)
            self.index_item(conn, item_id)
            self.write_index_md(conn)
            conn.commit()
            return self.get(item_id, with_body=False)

    def reconvert(self, item_id: str, *, conn: sqlite3.Connection) -> dict[str, Any]:
        """Re-run the conversion from the untouched original, keeping everything you wrote."""
        self._valid_id(item_id)
        with self.lock:
            cur = self.get(item_id, with_body=False)
            files = self.source_files(item_id)
            if not files:
                raise LibraryError("There is no original file to convert again.")
            data = files[0].read_bytes()
            keep = {k: cur.get(k) for k in ("title", "authors", "year", "venue", "doi", "url", "ref_id", "evidence_type",
                                            "reviewed", "tags", "notes", "added")}
            self._write_conversion(item_id, files[0].name, data, source_name=files[0].name, keep=keep)
            self.index_item(conn, item_id)
            conn.commit()
            return self.get(item_id, with_body=False)

    def update(self, item_id: str, patch: dict[str, Any], *, conn: sqlite3.Connection) -> dict[str, Any]:
        self._valid_id(item_id)
        with self.lock:
            p = self.ft_path(item_id)
            if not p.exists():
                raise LibraryError("Unknown item.")
            meta, body = parse_front_matter(p.read_text("utf-8", errors="replace"))
            for k, v in patch.items():
                if k not in EDITABLE:
                    continue
                if k == "year":
                    v = _int(v)
                if k in ("authors", "tags"):
                    if isinstance(v, str):
                        v = [x.strip() for x in re.split(r";|,|\n", v) if x.strip()] if k == "tags" else \
                            [x.strip() for x in re.split(r";|\n", v) if x.strip()]
                    v = [str(x).strip() for x in (v or []) if str(x).strip()][:60]
                if k == "doi" and v:
                    v = convert.clean_doi(str(v))
                if k == "reviewed":
                    v = bool(v)
                if k == "evidence_type" and v and v not in EVIDENCE_TYPES:
                    raise LibraryError("Unknown evidence type.")
                if k == "title" and not str(v or "").strip():
                    raise LibraryError("A title is required.")
                if v in (None, "", []):
                    meta.pop(k, None)
                else:
                    meta[k] = v
            meta["id"] = item_id
            _atomic_write(p, dump_front_matter(meta) + "\n" + body)
            self.index_item(conn, item_id)
            self.write_index_md(conn)
            conn.commit()
            return self.get(item_id, with_body=False)

    def write_actionable(self, item_id: str, body: str, status: str, *, conn: sqlite3.Connection) -> dict[str, Any]:
        self._valid_id(item_id)
        if status not in ("draft", "reviewed"):
            raise LibraryError("Status must be draft or reviewed.")
        if len(body) > 200_000:
            raise LibraryError("Those notes are too long.")
        with self.lock:
            cur = self.get(item_id, with_body=False)
            meta = {"title": cur.get("title"), "authors": cur.get("authors"), "year": cur.get("year"), "url": cur.get("doi") and
                    f"https://doi.org/{cur['doi']}" or cur.get("url"), "source": cur.get("source"),
                    "fulltext": f"2-fulltext/{item_id}.md", "evidence_type": cur.get("evidence_type"), "status": status,
                    "reviewed_on": date.today().isoformat() if status == "reviewed" else None, "tags": cur.get("tags")}
            _atomic_write(self.act_path(item_id), dump_front_matter(
                meta, ["title", "authors", "year", "url", "source", "fulltext", "evidence_type", "status", "reviewed_on", "tags"])
                + "\n" + body.strip() + "\n")
            self.index_item(conn, item_id)
            conn.commit()
            return self.read_actionable(item_id)

    def delete(self, item_id: str, *, conn: sqlite3.Connection) -> None:
        self._valid_id(item_id)
        with self.lock:
            for p in [self.ft_path(item_id), self.act_path(item_id), *self.source_files(item_id)]:
                p.unlink(missing_ok=True)
            self.index_item(conn, item_id)
            self.write_index_md(conn)
            conn.commit()

    # -- listing and search
    def list(self, conn: sqlite3.Connection, *, q: str = "", tag: str = "", status: str = "", reviewed: str = "",
             limit: int = 500) -> list[dict[str, Any]]:
        where, args = [], []
        snippets: dict[str, str] = {}
        terms = re.findall(r"[\w'À-ɏ]+", q or "")
        if terms:
            if self.fts:
                match = " ".join('"' + t.replace('"', "") + '"*' for t in terms)
                try:
                    rows = conn.execute("SELECT id, snippet(library_fts, 5, '[[', ']]', ' … ', 14) AS s FROM library_fts "
                                        "WHERE library_fts MATCH ? ORDER BY rank LIMIT 500", (match,)).fetchall()
                except sqlite3.OperationalError:
                    rows = []
                snippets = {r["id"]: r["s"] for r in rows}
                where.append("id IN (" + ",".join("?" * len(snippets)) + ")" if snippets else "0")
                args += list(snippets)
            else:
                for t in terms:
                    where.append("(title LIKE ? OR authors LIKE ? OR tags LIKE ?)")
                    args += [f"%{t}%"] * 3
        if tag:
            where.append("tags LIKE ?")
            args.append(f'%"{tag}"%')
        if status:
            where.append("status=?")
            args.append(status)
        if reviewed in ("0", "1"):
            where.append("reviewed=?")
            args.append(int(reviewed))
        sql = "SELECT * FROM library_items" + (" WHERE " + " AND ".join(where) if where else "") + \
              " ORDER BY added DESC, title COLLATE NOCASE LIMIT ?"
        out = []
        for r in conn.execute(sql, (*args, limit)):
            d = dict(r)
            d["tags"] = json.loads(d["tags"] or "[]")
            d["authors"] = [a for a in (d["authors"] or "").split(" ; ") if a]
            d["reviewed"] = bool(d["reviewed"])
            d["snippet"] = snippets.get(d["id"])
            out.append(d)
        if snippets:
            order = {k: i for i, k in enumerate(snippets)}
            out.sort(key=lambda d: order.get(d["id"], 1e9))
        return out

    def all_tags(self, conn: sqlite3.Connection) -> list[str]:
        tags: set[str] = set()
        for r in conn.execute("SELECT tags FROM library_items"):
            tags.update(json.loads(r["tags"] or "[]"))
        return sorted(tags, key=str.lower)

    def copies_by_ref(self, conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for r in conn.execute("SELECT id, ref_id, status FROM library_items WHERE ref_id IS NOT NULL AND ref_id != ''"):
            out[r["ref_id"]] = {"id": r["id"], "status": r["status"]}
        return out

    def write_index_md(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute("SELECT * FROM library_items ORDER BY title COLLATE NOCASE").fetchall()
        lines = ["# Library index", "", "Generated by the app; do not edit. Each source is kept in up to three forms "
                 "(see docs/ingest.md): your notes, the full-text conversion, and the untouched original.", "",
                 "| Source | Year | Status | Notes | Full text | Original |", "| --- | --- | --- | --- | --- | --- |"]
        for r in rows:
            title = (r["title"] or r["id"]).replace("|", "/")
            note = f"[notes](1-actionable/{r['id']}.md)" if r["notes_status"] else ""
            src = f"[{r['source'].split('/')[-1]}]({r['source']})" if r["source"] else ""
            lines.append(f"| {title} | {r['year'] or ''} | {r['status']}{' (reviewed)' if r['reviewed'] else ''} | {note} | "
                         f"[{r['id']}.md](2-fulltext/{r['id']}.md) | {src} |")
        _atomic_write(self.root / "INDEX.md", "\n".join(lines) + "\n")


def _int(v: Any) -> int | None:
    try:
        return int(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None
