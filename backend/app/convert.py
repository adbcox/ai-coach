"""Turn files and web pages into Markdown. No AI is involved: only off-the-shelf text extraction.

PDF -> pypdf (BSD-3). Web page -> trafilatura (Apache-2.0). Plain text and Markdown pass through.
Scanned PDFs (pictures of pages) contain no text, so they are kept as the original and flagged
"needs OCR"; OCR is not part of this image.

Nothing here talks to the network or the disk: callers pass bytes in and get text and metadata out.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import reflow

CONVERSION_VERSION = 2   # bump when conversion output improves; the Library then re-converts stored originals in the background
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp")
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.I)
YEAR_RE = re.compile(r"\b(19[5-9]\d|20[0-4]\d)\b")
_TRAILING = ".,;:)]}>'\""


@dataclass
class Converted:
    markdown: str = ""
    status: str = "converted"          # converted | needs_ocr | failed
    message: str = ""
    converter: str = ""
    pages: int | None = None
    title: str | None = None
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    url: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def clean_doi(raw: str) -> str:
    doi = raw.strip()
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", doi, flags=re.I)
    while doi and doi[-1] in _TRAILING:
        doi = doi[:-1]
    return doi.lower()


def find_doi(text: str) -> str | None:
    m = DOI_RE.search(text or "")
    return clean_doi(m.group(1)) if m else None


def word_count(md: str) -> int:
    return len(re.findall(r"\w+", md))


def pdf_to_markdown(data: bytes) -> Converted:
    from pypdf import PdfReader
    from pypdf import __version__ as pypdf_version
    from pypdf.errors import PyPdfError

    res = Converted(converter=f"pypdf {pypdf_version}")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            try:
                if not reader.decrypt(""):
                    res.status, res.message = "failed", "The PDF is password-protected."
                    return res
            except Exception:
                res.status, res.message = "failed", "The PDF is password-protected."
                return res
        pages_text: list[str] = []
        for page in reader.pages:
            try:
                pages_text.append(page.extract_text() or "")
            except Exception:
                pages_text.append("")
        info = reader.metadata
    except (PyPdfError, ValueError, OSError, KeyError, TypeError, AttributeError) as e:
        res.status, res.message = "failed", f"Could not read this PDF ({type(e).__name__})."
        return res

    res.pages = len(pages_text)
    total_chars = sum(len(t.strip()) for t in pages_text)
    if res.pages == 0 or total_chars < 200 * max(1, min(res.pages, 3)) * 0.5:
        res.status = "needs_ocr"
        res.message = ("This PDF has little or no selectable text (probably scanned pictures of pages). "
                       "The original is kept; text extraction (OCR) is not included in this image.")
        return res

    parts: list[str] = []
    for n, paras in enumerate(reflow.pages_to_paragraphs(pages_text), 1):
        if paras:
            parts.append(f"*\u2014 page {n} \u2014*\n\n" + "\n\n".join(paras))
    res.markdown = "\n\n".join(parts)

    first = reflow.normalize(pages_text[0]) if pages_text else ""
    res.doi = find_doi("\n".join(pages_text[:2]))
    if info is not None:
        t = str(info.get("/Title") or "").strip()
        if 8 <= len(t) <= 300 and not t.lower().endswith((".pdf", ".doc", ".docx", ".indd")) \
                and not t.lower().startswith(("microsoft word", "untitled")):
            res.title = t
        a = str(info.get("/Author") or "").strip()
        if a:
            res.authors = [p.strip() for p in re.split(r";|\band\b|,(?=\s*[A-Z][a-z]+\s+[A-Z])", a) if p.strip()][:40]
    if res.title is None:
        for ln in first.splitlines()[:12]:
            s = ln.strip()
            if 20 <= len(s) <= 220 and not re.match(r"^(https?://|www\.|doi|\d)", s, re.I):
                res.title = s
                break
    y = YEAR_RE.findall(first[:3000])
    if y:
        res.year = max(int(v) for v in y[:6])
    return res


def html_to_markdown(html: str, url: str | None = None) -> Converted:
    import trafilatura
    from trafilatura import extract, extract_metadata

    res = Converted(converter=f"trafilatura {getattr(trafilatura, '__version__', '')}".strip(), url=url)
    try:
        md = extract(html, url=url, output_format="markdown", include_links=True, include_tables=True,
                     include_comments=False, favor_recall=True)
        meta = extract_metadata(html, default_url=url)
    except Exception as e:  # trafilatura raises many kinds of errors on odd pages
        res.status, res.message = "failed", f"Could not read this page ({type(e).__name__})."
        return res
    if not md or word_count(md) < 80:
        res.status = "failed"
        res.message = ("Not enough readable text was found. The page may need JavaScript, be behind a paywall or login, "
                       "or only show an abstract. Download the PDF and upload it instead.")
        return res
    res.markdown = md.strip()
    if meta is not None:
        res.title = (meta.title or "").strip() or None
        if meta.author:
            res.authors = [a.strip() for a in re.split(r";|\band\b", meta.author) if a.strip()][:40]
        if meta.date:
            m = YEAR_RE.search(str(meta.date))
            res.year = int(m.group(1)) if m else None
        res.venue = (meta.sitename or meta.hostname or "") or None
    res.doi = find_doi(html[:60000])
    return res


def text_to_markdown(data: bytes, *, markdown: bool) -> Converted:
    for enc in ("utf-8-sig", "utf-16", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeError:
            continue
    else:
        return Converted(status="failed", message="Could not decode this file as text.")
    res = Converted(markdown=text.strip(), converter="copied as is")
    if not res.markdown:
        res.status, res.message = "failed", "The file is empty."
        return res
    m = re.search(r"^#\s+(.+)$", res.markdown, re.M) if markdown else None
    first = next((ln.strip() for ln in res.markdown.splitlines() if ln.strip()), "")
    res.title = (m.group(1).strip() if m else first[:200]) or None
    res.doi = find_doi(res.markdown[:5000])
    return res


def convert(filename: str, data: bytes) -> tuple[Converted, str]:
    """Pick a converter from the file's content and name. Returns (result, extension to store the original as)."""
    low = filename.lower()
    if data[:5] == b"%PDF-" or low.endswith(".pdf"):
        return pdf_to_markdown(data), ".pdf"
    if low.endswith((".html", ".htm", ".xhtml")) or data[:200].lstrip().lower().startswith((b"<!doctype html", b"<html")):
        return html_to_markdown(data.decode("utf-8", "replace")), ".html"
    if low.endswith((".md", ".markdown")):
        return text_to_markdown(data, markdown=True), ".md"
    if low.endswith((".txt", ".text")):
        return text_to_markdown(data, markdown=False), ".txt"
    if low.endswith(IMAGE_EXTS):
        stem = re.sub(r"[_-]+", " ", Path(filename).stem).strip()
        return Converted(status="needs_ocr", pages=1, title=stem or None,
                         message="This is a picture, so its text has to be read with OCR."), Path(filename).suffix.lower()
    return Converted(status="failed", message=(
        "This file type is not supported yet. Supported: PDF, web pages (.html), Markdown and text. "
        "Pictures (.png, .jpg, ...) and scanned PDFs are read with OCR.")), ""
