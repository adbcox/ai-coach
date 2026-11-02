# Ingest area

- Lives on the server's mounted volume (`data/ingest/`), **never in git and never in the Docker image**.
- **Built in v0.6.0 as the Library** (the Library tab): conversion to Markdown with no AI, search, your own notes, citations.
  Scanned PDFs and pictures are read automatically with OCR (v0.6.2). Still to come: automatic distillation into `1-actionable/` (needs an AI connection), layout-aware tables, and YouTube transcripts (a heavier `full` image).

## What v0.6.0 does

| You do | The app does |
| --- | --- |
| Drop one or many files on the Library page (PDF, scanned PDF, picture, `.html`, `.md`, `.txt`) | Keeps the original in `3-source/`, converts it to `2-fulltext/<id>.md` with a front-matter header (title, authors, year, DOI, converter, page and word counts), de-duplicates by file hash and DOI |
| Paste a DOI | Looks up the citation on Crossref (only the DOI is sent) and saves a *citation only* entry you can attach the PDF to later |
| Paste a link to an article or PDF | Downloads it (only public internet addresses are allowed), converts it with trafilatura or pypdf. Publisher pages that block automated downloads are reported, and you upload the PDF instead |
| Type a citation | Saves a *citation only* entry |
| Copy files into `ingest/inbox/` on the server | Converts them on the next scan (within a minute, or press **Scan folder**) |
| Write notes on a paper | Saves them as `1-actionable/<id>.md` from the template below, status `draft` until you mark it `reviewed` |
| Edit tags, evidence type, details | Rewrites the header of the Markdown file; the files stay the source of truth and the search index is rebuilt from them |
| Search | Full-text search across titles, authors, tags, your notes and the paper text (SQLite FTS5) |

Cleaning and OCR (v0.6.2): PDF text arrives line by line as it was typeset, so the converter rejoins words split across lines, joins
hard-wrapped lines into paragraphs, fixes ligatures and drops running headers and page numbers, all with plain rules (no AI, so it can
never change a number). Scanned PDFs and pictures are read with Tesseract in the background, page by page, and every OCR'd item is
labelled with its confidence. When the converter improves (`CONVERSION_VERSION` in `convert.py`), stored originals are re-converted
automatically and everything you wrote (tags, notes, details, reviewed flag) is kept.

Honest limits: tables, figures, equations (an exponent can come out as a plain character) and two-column layouts do not convert
faithfully, and OCR can misread digits and symbols. The Library says so on every item and keeps the original so a better converter
can re-run later ("Convert again", "Read the scan again"). Page markers (`— page 3 —`) are inserted so a note can point to where a claim is.

## Retrieval order (how the model uses these)

1. Read `1-actionable/` first. Answer from it when it is sufficient.
2. If an item's conditions, caveats or reasoning are unclear or matter
   for the decision, open the matching `2-fulltext/` file (the item's
   "Where" pointer says which section/timestamp).
3. Only if `2-fulltext/` is still insufficient (conversion looks wrong,
   figure/table lost, ambiguity in the original), go to `3-source/`.
4. Say which tier an answer came from, and flag any `draft` file.

## Format

Everything is Markdown with YAML front matter, not a database. The files
are the source of truth; any database/vector index (v0.6+) is generated
from the front matter and can be rebuilt.

All three versions of every source are linked in an `INDEX.md` kept in the ingest folder on the server.

## Input types and off-the-shelf tools (researched 2026-11-01)

Everything lands in `3-source/` as-is (for links: a small `.url` file or
the saved page), then converts to `2-fulltext/`. All tools below are
open source; none was run yet, and benchmark figures are from secondary
sources.

| Input | Tool | Notes |
| --- | --- | --- |
| `.txt` / `.md` | none | Copy through, add front matter |
| PDF (text or scanned), images/screenshots | [Docling](https://github.com/docling-project/docling) | Layout + tables + OCR built in; heavier/slower. Reported 0.882 vs MarkItDown 0.589 on one benchmark |
| Office docs, HTML, misc. | [MarkItDown](https://github.com/microsoft/markitdown) | Fast, 15+ formats, but no bundled OCR; weak on scanned PDFs/dense tables |
| Article URL | [Trafilatura](https://github.com/adbar/trafilatura) | F1 0.912 vs readability-lxml 0.804 (peer-reviewed, Barbaresi 2021) |
| YouTube URL | youtube-transcript-api → yt-dlp subtitles → yt-dlp audio + faster-whisper | Tiered fallback: captions first, local transcription only if none |

Plan: Docling as the default converter, MarkItDown/Trafilatura for the
types they handle better, Whisper only as a last resort. Always keep the
tool name/version in the `2-fulltext/` front matter, and have the
verification pass spot-check OCR'd and transcribed files (OCR and ASR
errors are exactly where numbers and names get corrupted).

## Rules

- Never edit `3-source/`. `2-fulltext/` and `1-actionable/` are regenerable from it.
- Every `2-fulltext/` and `1-actionable/` file starts with a header: title,
  authors/channel, year, URL or DOI, date ingested, source file in
  `3-source/`. Cite peer-reviewed sources first; prefer the last 5 years.
- `1-actionable/` rules of thumb:
  - Paper: findings, effect sizes, population, recommendations. Skip
    methodology unless it limits who the result applies to.
  - Video/podcast: the 3–10 practical takeaways, not the transcript
    (a 16-minute video rarely needs more than a page).
  - Always note confidence and whether it applies to the athlete (age, volume,
    recreational vs. elite).
- Source files are **not committed to git** (the build repo is public;
  copyright and personal data). The ingest folders live on a mounted
  volume on the server running the container.

## Actionable file safeguards (so context isn't lost)

Short is fine; *unanchored* short is not. Every `1-actionable/` file uses
this template:

```markdown
---
title: <title>
authors: <authors/channel>
year: <year>
url: <DOI/URL>
source: 3-source/<file>
fulltext: 2-fulltext/<file>.md
evidence_type: RCT | meta-analysis | observational | coach opinion | anecdote
status: draft | reviewed
reviewed_on: <date or empty>
tags: []
---

## Items
1. **Claim/action:** <one sentence>
   - **Applies to:** population, level, volume, conditions (e.g. "trained
     runners, 8-wk block, ≥40 km/wk")
   - **Size/strength:** effect size or "no numbers given"; confidence
   - **Where:** page/section or timestamp in 2-fulltext/ (+ short verbatim quote)
   - **Caveats:** what would make this wrong or not apply to the athlete

## Conflicts with other sources
<links to other actionable files that disagree, or "none known">

## Omitted
<one line per category cut: methodology, background, tangents, ads…>
```

Rules that prevent silent loss:

- **Every item cites its location** in `2-fulltext/` and carries its conditions.
  An item with no "Applies to" is not allowed — most misleading advice
  is a true finding stripped of its population.
- **Evidence vs. opinion is labelled.** Videos mix both; never present
  an opinion as a finding.
- **The Omitted section is mandatory**, so a reviewer can see what was
  cut and object.
- **Verification pass (second AI pass, separate from the distiller):**
  checks each item against `2-fulltext/` (supported? caveat dropped?) and scans
  `2-fulltext/` for important claims missing from `1-actionable/`.
- **Human review gate:** files stay `draft` until the athlete marks them reviewed;
  the agent should flag when it relies on a draft.
- **Conflicts are kept, not averaged.** If two sources disagree, both
  stay, linked to each other.
- **Coach follows the retrieval order above** when an item's caveats
  matter for a decision.

## Workflow (see [roadmap](roadmap.md))

1. Add file to `3-source/`.
2. Conversion tools (no LLM needed) produce `2-fulltext/` (v0.3).
3. A connected agent distils `2-fulltext/` into `1-actionable/` (v0.5) using the template above.
4. Verification pass, then athlete review before status becomes `reviewed`.
