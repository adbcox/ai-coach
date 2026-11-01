# Roadmap

The whole app works with no AI until v0.5.

| Version | Step | Scope |
| --- | --- | --- |
| v0.1 | 0 — Garmin ingest | First-run setup creates the single admin account; a settings page where the admin enters the Garmin API key (never via chat, repo or build; stored only on the server volume); sync via the [Garmin Personal API](garmin.md) into SQLite on the container volume, behind a provider interface so other providers can be added later. Per-second samples via FIT download (confirm the personal key can fetch FIT files first). |
| v0.2 | 1 — Dashboard/GUI | Desktop-first. Mileage for the last 14 days; single-run detail view including a GPX/map view with linked charts. Uses the v0.1 admin login. |
| v0.3 | 2 — Literature ingest | Upload a file or paste a link; off-the-shelf OCR/extraction tools convert it into the [three ingest tiers](ingest.md). No LLM needed. |
| v0.4 | 3 — Recovery | Sleep, HRV, Body Battery and stress in the dashboard. |
| v0.5 | 4 — AI integration | REST API + MCP server so any agent (local model, Claude, ChatGPT, Codex, ...) can connect; actionable distillation of ingested sources; plan-adjustment assistant. |
| v0.6+ | — | Research-grounding approach (how an agent selects research: RAG, curated corpus, ...); additional data providers (e.g. Strava export). |
| v0.7 | — | Mobile-friendly website (responsive layouts). |
| v0.8 | — | Installable web app (PWA): home-screen icon, full-screen, fast loads. |
| v1.0 | — | Used to adjust real training weeks, reliably. |
| Later | — | Multi-user accounts (each user with their own Garmin key), way down the road. |

## Decided so far

- **Stack (approved 2026-11-01):** Python + FastAPI backend; React + TypeScript (Vite) single-page app, built into the same Docker image (multi-stage build, Node only at build time); SQLite (WAL mode); two image tags: `slim` (sync, dashboard, agent access) and `full` (adds ingest converters: Docling, etc., CPU-only PyTorch). Chart and map libraries (e.g. uPlot/ECharts, MapLibre/Leaflet) to be chosen at v0.2, with a license check.
- Single container; SQLite-class embedded storage; runs on a small box (Intel N100, 16 GB) and portable to a cloud host.
- The Garmin API key is entered by the user in the running app's settings page (no env var, never shared with the developer or an AI). Needs the admin login from v0.1. Development and tests use recorded fixtures, not a real key.
- MVP targets desktop. Single admin user with built-in login (safe if later exposed publicly).
- Mobile site, then installable web app, then multi-user, in that order.

## Open items

- ~~Confirm FIT file download works with a Garmin personal key~~: confirmed for one cycling activity (see [Garmin docs](garmin.md)); still to test older activities and runs.
- Revisit DuckDB/Parquet only if analysis outgrows SQLite.
- ~~Check dependency licenses~~: done, see [licenses](licenses.md). No change to MIT needed.
- Read Garmin's Personal API Terms and Conditions (shown only when creating a key; the public docs page covers setup steps, not the terms text) regarding AI use. Still unread.
