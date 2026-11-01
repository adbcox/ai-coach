# Roadmap

The whole app works with no AI until v0.5.

| Version | Step | Scope |
| --- | --- | --- |
| v0.1 | 0 — Garmin ingest | Sync via the [Garmin Personal API](garmin.md) into SQLite on the container volume, behind a provider interface so other providers can be added later. Per-second samples via FIT download (confirm the personal key can fetch FIT files first). |
| v0.2 | 1 — Dashboard/GUI | Mileage for the last 14 days; single-run detail view including a GPX/map view. |
| v0.3 | 2 — Literature ingest | Upload a file or paste a link; off-the-shelf OCR/extraction tools convert it into the [three ingest tiers](ingest.md). No LLM needed. |
| v0.4 | 3 — Recovery | Sleep, HRV, Body Battery and stress in the dashboard. |
| v0.5 | 4 — AI integration | REST API + MCP server so any agent (local model, Claude, ChatGPT, Codex, ...) can connect; actionable distillation of ingested sources; plan-adjustment assistant. |
| v0.6+ | — | Research-grounding approach (how an agent selects research: RAG, curated corpus, ...); additional data providers (e.g. Strava export). |
| v1.0 | — | Used to adjust real training weeks, reliably. |

## Open items

- ~~Confirm FIT file download works with a Garmin personal key~~: confirmed for one cycling activity (see [Garmin docs](garmin.md)); still to test older activities and runs.
- Pick the stack (Python assumed: the chosen ingest tools are Python) and the embedded database (SQLite default; DuckDB/Parquet if analysis outgrows it).
- ~~Check dependency licenses~~: done, see [licenses](licenses.md). No change to MIT needed.
- Read Garmin's Personal API Terms and Conditions (shown only when creating a key; the public docs page covers setup steps, not the terms text) regarding AI use. Still unread.
