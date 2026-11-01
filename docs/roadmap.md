# Roadmap

The whole app works with no AI until v0.5.

| Version | Step | Scope |
| --- | --- | --- |
| v0.1 | 0 — Garmin ingest | **Built and in use** (full history and daily health data synced from a real account). First-run setup creates the single admin account; a settings page where the admin enters the Garmin API key (never via chat, repo or build; stored only on the server volume); sync via the [Garmin Personal API](garmin.md) into SQLite on the container volume, behind a provider interface so other providers can be added later. Per-second samples via FIT download. Pulls the entire activity history and all daily health data (sleep, HRV, Body Battery, summaries, heart rate, SpO2, steps, hydration, weight) as raw JSON, then keeps both up to date incrementally: a per-source automatic sync interval (Settings), a home-page quick sync (24-hour lookback) and 30-day-lookback background syncs, all anchored to the newest stored data. Done in the v0.1 skeleton; first live sync verified by the user. |
| v0.2 | 1 — Dashboard/GUI | **First version built.** Desktop-first. Last-14-days dashboard (daily distance by sport, last 7 vs previous 7 days, sport filter, latest activities) and a single-run detail view: map of the route, pace/speed, heart rate, elevation, power and cadence charts linked to a moving map marker, training load and training effect when Garmin provides them, and GPX download. Uses the v0.1 admin login. Also: 4-week rolling 7-day average distance and rolling 7-day longest run line charts. Still to do: tune against real data (the data-shapes file), and confirm the "weekly mileage last 14 days" interpretation. |
| v0.2.1 | Backup and restore | **Built.** Download-able `.tar` backups (consistent database snapshot, original Garmin files, ingest folders; master key excluded; optional passphrase-sealed Garmin key), kept on the server (newest 7), restore on a fresh install from the first-run screen or over an existing install from Settings (previous database kept). Checked end to end in a browser across two instances. |
| v0.2.2 | Scheduled backups to an SMB share (substep of backup) | **Built.** Settings form with connection test, interval (6 h to weekly, or manual only), retention, status; encrypted share password; upload size-verified; scheduled backups exclude the Garmin key. Verified over the real SMB2 protocol against a test server (connect, folder creation, upload, listing, prune); not yet run against your own NAS. |
| v0.3 | 2 — Literature ingest | Upload a file or paste a link; off-the-shelf OCR/extraction tools convert it into the [three ingest tiers](ingest.md). No LLM needed. |
| v0.4 | 3 — Recovery | **First version built (v0.2.0).** Recovery page with sleep score and duration (deep/REM), HRV with Garmin's balanced range, resting heart rate, Body Battery and stress, over 30 days to 1 year, parsed from the real response shapes (see [Garmin docs](garmin.md)). Still to do: sleep-stage detail, intraday Body Battery, readiness-style summary, link recovery to training load. |
| v0.5 | 4 — AI integration | REST API + MCP server so any agent (local model, Claude, ChatGPT, Codex, ...) can connect; actionable distillation of ingested sources; plan-adjustment assistant. |
| v0.6+ | — | Research-grounding approach (how an agent selects research: RAG, curated corpus, ...); additional data providers (e.g. Strava export). |
| Providers (queued) | — | **Strava** and **COROS** are the first additional connections. Strava: its API terms reportedly prohibit using API data with AI applications, so plan on the one-time personal data export (not the API) until that is re-checked. COROS: how a personal user can get data out (API access, export files) has not been researched yet. Each plugs in through the provider interface (source + source id per activity). |
| With 2nd provider | — | Cross-source linking and de-duplication: when more than one source is connected, match the same activity across them (e.g. Garmin and a Strava export) into one record so totals are not double counted. Keep each source's original record and link them, with a rule for which source wins per field. |
| Next | HR zones on charts | **First version built (v0.2.1)**: zone bands behind the heart-rate line on the run detail chart in Strava's colours (Zone 1 grey, 2 blue, 3 green, 4 orange, 5 red), estimated from your max heart rate (editable in Settings, default = highest recorded) at Garmin's default 50/60/70/80/90%. Garmin's own zone settings are now also collected (raw, from the heart-rate-zones endpoint) so the next step is to read their real boundaries, per sport and over time, instead of estimating. The per-activity time-in-zone bars come from Garmin and use the same colours. |
| Next | Rebuild from stored files | Settings button that re-parses every archived Garmin download (`data/activities/garmin/*.zip`) into the database without contacting Garmin, so parser improvements (more per-second fields such as ground contact, vertical oscillation, stride and temperature; laps; device info) apply to old activities too. The zips are the original downloads and also the compact long-term archive (about 60% smaller than plain .fit files). |
| v0.7 | — | Mobile-friendly website (responsive layouts). |
| v0.8 | — | Installable web app (PWA): home-screen icon, full-screen, fast loads. |
| v1.0 | — | Used to adjust real training weeks, reliably. |
| Later | — | Multi-user accounts (each user with their own Garmin key), way down the road. |

## Decided so far

- **Stack (approved 2026-11-01):** Python + FastAPI backend; React + TypeScript (Vite) single-page app, built into the same Docker image (multi-stage build, Node only at build time); SQLite (WAL mode); two image tags planned: `slim` (sync, dashboard, agent access; the only one built so far) and `full` (adds ingest converters: Docling, etc., CPU-only PyTorch; arrives with literature ingest). Chart and map libraries (e.g. uPlot/ECharts, MapLibre/Leaflet) to be chosen at v0.2, with a license check.
- Single container; SQLite-class embedded storage; runs on a small box (Intel N100, 16 GB) and portable to a cloud host.
- The Garmin API key is entered by the user in the running app's settings page (no env var, never shared with the developer or an AI). Needs the admin login from v0.1. Development and tests use recorded fixtures, not a real key.
- Garmin API key is encrypted at rest with a master key generated on first run and stored separately from the database (owner-only permissions); an optional environment variable or Docker secret overrides it (use this on a cloud host).
- MVP targets desktop. Single admin user with built-in login (safe if later exposed publicly).
- Mobile site, then installable web app, then multi-user, in that order.

## Backup design notes (for v0.2.1 / v0.2.2)

- Use SQLite's online backup, not a file copy, so a snapshot is consistent while syncing.
- The activity ZIPs are the original Garmin files, so they are also the safest long-term copy; they can be incrementally synced rather than re-archived each time.
- The master key stays out of ordinary backups (a backup containing both the database and its key defeats the encryption). Portable option: passphrase-encrypted archive.
- SMB credentials get the same encryption-at-rest as the Garmin key. Verify the share is reachable and writable when saving settings, and report backup failures in the UI.

## Open items

- ~~Confirm FIT file download works with a Garmin personal key~~: confirmed at scale (449 of 452 activities in one account have per-second data; see [Garmin docs](garmin.md)).
- Revisit DuckDB/Parquet only if analysis outgrows SQLite.
- ~~Check dependency licenses~~: done, see [licenses](licenses.md). No change to MIT needed.
- Read Garmin's Personal API Terms and Conditions (shown only when creating a key; the public docs page covers setup steps, not the terms text) regarding AI use. Still unread.
