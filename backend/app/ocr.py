"""OCR for scanned PDFs and images: pypdfium2 draws each page, Tesseract reads it.

Tesseract (Apache-2.0) is a separate program installed in the Docker image; pypdfium2 (BSD-3 / Apache-2.0) and Pillow draw the
pages. Nothing is sent anywhere: it all runs on your server, one page at a time, in the background.

OCR makes mistakes, especially with numbers, symbols and tables, so every page gets a confidence score and the result is always
labelled as OCR in the Library.
"""

from __future__ import annotations

import io
import os
import re
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field

from . import reflow

os.environ.setdefault("OMP_THREAD_LIMIT", "2")  # keep a small NAS responsive while a long scan is read

MAX_PAGES = 400
RENDER_DPI = 250
LOW_CONFIDENCE = 70
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp", ".bmp")


class OcrError(Exception):
    pass


@dataclass
class OcrResult:
    markdown: str = ""
    pages: int = 0
    confidence: float | None = None        # mean word confidence, 0-100
    low_pages: list[int] = field(default_factory=list)
    engine: str = ""
    chars: int = 0


def available() -> bool:
    return shutil.which("tesseract") is not None


def engine_name() -> str:
    try:
        import pytesseract
        return f"tesseract {pytesseract.get_tesseract_version()}"
    except Exception:
        return "tesseract"


def _page_text(img, langs: str) -> tuple[str, float | None]:
    import pytesseract
    from pytesseract import Output

    d = pytesseract.image_to_data(img, lang=langs, output_type=Output.DICT, config="--psm 3")
    paras: dict[tuple[int, int], dict[int, list[str]]] = {}
    confs: list[float] = []
    for i, word in enumerate(d["text"]):
        w = (word or "").strip()
        if not w:
            continue
        try:
            c = float(d["conf"][i])
        except (TypeError, ValueError):
            c = -1
        if c >= 0:
            confs.append(c)
        paras.setdefault((d["block_num"][i], d["par_num"][i]), {}).setdefault(d["line_num"][i], []).append(w)
    out = []
    for key in sorted(paras):
        lines = [" ".join(ws) for _, ws in sorted(paras[key].items())]
        out.append(re.sub(r"(?<=[A-Za-z])-\n(?=[a-z])", "", "\n".join(lines)))
    return "\n\n".join(out), (sum(confs) / len(confs) if confs else None)


def _images(data: bytes, filename: str):
    """Yield (page number, PIL image, total pages) for a PDF or an image file."""
    from PIL import Image

    if data[:5] == b"%PDF-" or filename.lower().endswith(".pdf"):
        import pypdfium2 as pdfium
        try:
            pdf = pdfium.PdfDocument(data)
        except Exception as e:
            raise OcrError(f"Could not open the PDF to read its pages ({type(e).__name__}).") from e
        total = min(len(pdf), MAX_PAGES)
        for n in range(total):
            page = pdf[n]
            try:
                yield n + 1, page.render(scale=RENDER_DPI / 72).to_pil().convert("L"), total
            finally:
                page.close()
        pdf.close()
    else:
        try:
            img = Image.open(io.BytesIO(data))
            frames = getattr(img, "n_frames", 1)
            total = min(frames, MAX_PAGES)
            for n in range(total):
                img.seek(n)
                yield n + 1, img.convert("L"), total
        except Exception as e:
            raise OcrError(f"Could not open the image ({type(e).__name__}).") from e


def ocr_document(data: bytes, filename: str, *, langs: str = "eng",
                 progress: Callable[[int, int], None] | None = None) -> OcrResult:
    if not available():
        raise OcrError("Tesseract is not installed in this environment.")
    raw_pages: list[tuple[int, str, float | None]] = []
    weighted = 0.0
    words_total = 0
    low: list[int] = []
    chars = 0
    total = 0
    for n, img, total in _images(data, filename):
        try:
            text, conf = _page_text(img, langs)
        except Exception as e:
            raise OcrError(f"Tesseract failed on page {n} ({type(e).__name__}).") from e
        chars += len(text.strip())
        if conf is not None:
            nwords = max(1, len(text.split()))
            weighted += conf * nwords
            words_total += nwords
            if conf < LOW_CONFIDENCE and nwords >= 20:
                low.append(n)
        if text.strip():
            raw_pages.append((n, text, conf))
        if progress:
            progress(n, total)
    vocab = reflow.vocabulary(reflow.normalize("\n".join(t for _, t, _ in raw_pages)))
    parts: list[str] = []
    for n, text, conf in raw_pages:
        paras = reflow.paragraphs_from_text(text, vocab)
        note = (f"\n\n*(OCR confidence on this page is low, {conf:.0f}%: check it against the original.)*"
                if n in low and conf is not None else "")
        parts.append(f"*\u2014 page {n} \u2014*\n\n" + "\n\n".join(paras) + note)
    return OcrResult(markdown="\n\n".join(parts), pages=total, confidence=(weighted / words_total if words_total else None),
                     low_pages=low, engine=engine_name(), chars=chars)
