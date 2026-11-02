"""Turn the line-by-line text a PDF (or OCR) gives into readable paragraphs.

PDF text arrives as it was typeset: one line at a time, words split across lines with a hyphen ("monitor -" / "ing"), running
page headers and page numbers mixed in, and typographic ligatures. This module repairs those things with plain rules; it never
guesses at content. It cannot rebuild tables, figures or equations, which stay as they come out.
"""

from __future__ import annotations

import re
from collections import Counter

_LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st",
              " ": " ", "​": "", "­": "-", "‐": "-", "‑": "-"}
_LIG_RE = re.compile("|".join(map(re.escape, _LIGATURES)))
_WORD_RE = re.compile(r"[^\W\d_]+(?:-[^\W\d_]+)*", re.UNICODE)
# a line that ends in a hyphen (also "monitor -", as some PDF fonts give it) and the next line starts with a lowercase letter
_HYPH_END = re.compile(r"([^\W\d_])\s?-$", re.UNICODE)
_LIST_START = re.compile(r"^(\d{1,2}[.)]\s|[•▪●◦*]\s|[-–]\s\S|(Table|Figure|Fig\.|Box|Appendix)\s+[\dA-Z])")
_SENTENCE_END = re.compile(r"[.!?:;”\")\]]$")


def normalize(text: str) -> str:
    return _LIG_RE.sub(lambda m: _LIGATURES[m.group(0)], text)


def vocabulary(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text)}


def _join_hyphenated(left: str, right: str, vocab: set[str]) -> str:
    """Rejoin a word split over two lines. `left` ends with the hyphen, `right` starts with the rest of the word."""
    stem = _HYPH_END.sub(r"\1", left)               # drops the hyphen and any space before it
    m_left = re.search(r"([^\W\d_]+)$", stem, re.UNICODE)
    m_right = re.match(r"([^\W\d_]+)(.*)$", right, re.UNICODE)
    if not (m_left and m_right):
        return stem + " " + right
    a, b = m_left.group(1), m_right.group(1)
    if (a + b).lower() in vocab:
        return stem + right                         # "monitor-" + "ing" -> "monitoring" (the word occurs elsewhere whole)
    if f"{a}-{b}".lower() in vocab:
        return stem + "-" + right                   # a real compound the document itself writes with a hyphen
    return stem + right                             # most line-end hyphens are just line breaks


def paragraphs_from_lines(lines: list[str], vocab: set[str], *, short_rule: bool = True) -> list[str]:
    """Join hard-wrapped lines into paragraphs. A paragraph ends at a blank line, after a clearly short line, or before a list item."""
    lines = [ln.strip() for ln in lines]
    lens = sorted(len(ln) for ln in lines if len(ln) >= 25)
    typical = lens[int(len(lens) * 0.8)] if (lens and short_rule) else 0
    out: list[str] = []
    cur = ""
    for i, ln in enumerate(lines):
        if not ln:
            if cur:
                out.append(cur)
                cur = ""
            continue
        if cur:
            if _HYPH_END.search(cur) and ln[:1].islower():
                cur = _join_hyphenated(cur, ln, vocab)
            else:
                cur = f"{cur} {ln}"
        else:
            cur = ln
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        mid_sentence = (nxt[:1].islower() and not _SENTENCE_END.search(ln)) or bool(re.search(r"\s[-\u2013]$", ln))   # a short line followed by a lowercase line is not a paragraph end
        short = typical and len(ln) < 0.62 * typical and not mid_sentence
        if not nxt or _LIST_START.match(nxt) or (short and not (_HYPH_END.search(ln) and nxt[:1].islower())):
            out.append(cur)
            cur = ""
    if cur:
        out.append(cur)
    return [re.sub(r"[ \t]{2,}", " ", p).strip() for p in out if p.strip()]


def strip_running_headers(pages: list[list[str]]) -> list[list[str]]:
    """Remove page numbers and headers/footers that repeat on most pages (journal name, running title, 'Downloaded from ...')."""
    if len(pages) < 3:
        return pages

    def key(s: str) -> str:
        return re.sub(r"\d+", "#", s.strip().lower())

    counts: Counter[str] = Counter()
    for p in pages:
        nonblank = [ln for ln in p if ln.strip()]
        for ln in {key(x) for x in nonblank[:3] + nonblank[-3:] if len(x.strip()) <= 120}:
            counts[ln] += 1
    repeated = {k for k, n in counts.items() if n >= max(3, len(pages) * 0.4) and k not in ("", "#")}
    cleaned = []
    for p in pages:
        nonblank_idx = [i for i, ln in enumerate(p) if ln.strip()]
        edge = set(nonblank_idx[:3] + nonblank_idx[-3:])
        keep = []
        for i, ln in enumerate(p):
            s = ln.strip()
            if i in edge and s and (key(s) in repeated or re.fullmatch(r"[-–]?\s*\d{1,4}\s*[-–]?", s)):
                continue
            keep.append(ln)
        cleaned.append(keep)
    return cleaned


def pages_to_paragraphs(page_texts: list[str]) -> list[list[str]]:
    """Per page, a list of clean paragraphs."""
    pages = [normalize(t).splitlines() for t in page_texts]
    pages = strip_running_headers(pages)
    vocab = vocabulary(normalize("\n".join(page_texts)))
    return [paragraphs_from_lines(p, vocab) for p in pages]


def paragraphs_from_text(text: str, vocab: set[str]) -> list[str]:
    """For text that is already split into paragraphs by blank lines (OCR output): only join the wrapped lines inside each."""
    out: list[str] = []
    for block in re.split(r"\n\s*\n", normalize(text)):
        out.extend(paragraphs_from_lines(block.splitlines(), vocab, short_rule=False))
    return out
