<p align="center"><img src="frontend/public/logo.svg" width="96" alt="AI Endurance Coach logo"></p>

# AI Endurance Coach

Self-hosted, AI-optional endurance training dashboard: Garmin sync, run analysis and a literature ingest area, in a single Docker container.

**Mission: use your data to train smarter, and always show the math.** You should know how the sausage is made, so every number should be traceable to the data and formula behind it.

> **Status: pre-alpha, but usable.** Garmin sync (full history), dashboard, run detail with map and charts, recovery page, backups (including to a network share) and a first-run setup all work. Literature ingest and agent (AI) access are next. See the [roadmap](docs/roadmap.md), [changelog](CHANGELOG.md) and [install guide](docs/install.md). Default port: **26219**.

## Disclaimer: vibe-coded, use at your own risk

This project was largely written with AI assistance ("vibe-coded") and has not had a professional security or safety review. It is provided **as is**, with no warranty (see the [MIT license](LICENSE)).

- **Digital risk:** it handles your Garmin API key and personal health data. Bugs, misconfiguration or exposing it to the internet could leak or lose that data. Keep it on a trusted network or behind a VPN/authenticating proxy, use HTTPS if exposed, back up your data volume, and revoke your Garmin key if in doubt.
- **Physical risk:** training metrics, plans or AI-generated suggestions may be wrong. This is not medical advice and is not a substitute for a qualified coach or doctor. Do not push through pain, illness or injury because a dashboard said so. You are responsible for your own training decisions.
- **Garmin terms:** use only your own data with your own key, and read Garmin's terms yourself.

## Principles

- **Open and explainable.** The point of the app is to give you tools to plan with that you can understand. Every number should show where it came from and how it was calculated, predictions should show their working and their uncertainty, and the science behind them should be cited.
- **Self-contained, AI-optional.** One Docker container. Sync, storage, dashboard and ingest all work with no AI.
- **Bring your own agent.** The same data and ingest area will be exposed through a REST API and an MCP server, so you can connect a local model, Claude, ChatGPT, Codex or anything else (roadmap v0.5).
- **Public code, private data.** Your Garmin key, health data and ingested files stay on the server running your container, on a mounted volume. They are never in this repo (see `.gitignore`).
- **Your own data only.** Garmin's Personal API is licensed for personal use with your own data. Each user runs their own instance with their own key.

## What it does today

- **Garmin sync**: your whole activity history (with per-second data) plus daily health data (sleep, HRV, Body Battery, stress, resting heart rate, steps, ...), kept up to date automatically (interval set in Settings; quick sync button on the dashboard).
- **Dashboard**: last 14 days of distance by sport, rolling weekly mileage (km per week) and rolling 7-day longest run, over the last 4 weeks. Opens on the sport you choose in Settings (Running by default).
- **Activities and run detail**: filterable list; per-run map, laps (Garmin's splits, usually every 1 km), pace/speed, heart rate (with zone bands), elevation, power and cadence charts linked to the map, heart-rate zone time, running dynamics, GPX download.
- **Race predictions**: 5K, 10K, half marathon and marathon from your own best efforts (hills and trail handled with grade-adjusted pace; treadmill included; mark real races to check the predictions against them), using several established methods side by side. Each number opens into the formula with your numbers filled in, the uncertainty, a back-test against your own history, and the sources. See [how it works](docs/predictions.md).
- **Max heart rate and VO2max**: max heart rate estimated from your own recorded peaks (not a formula), and VO2max estimated several ways side by side, each with its working, range and limits.
- **Recovery**: sleep score and duration, HRV against your balanced range, resting heart rate, Body Battery and stress, 30 days to 1 year.
- **Library**: drop in PDFs, web pages, Markdown or text (many at once), paste links or DOIs, or type a citation. Each source becomes a Markdown file you can read in the app and on disk, with the original kept; search across the full text, tag and annotate, and write your own notes. No AI involved; your files stay on your server and are never part of the image or git. See [docs/ingest.md](docs/ingest.md).
- **On your phone**: the whole app works in a phone browser, with a bottom tab bar and charts you can scrub with a finger (an installable app comes later).
- **Backups**: one-click portable backup and restore (move to a new machine), plus scheduled uploads to an SMB network share. Your Garmin key is encrypted at rest and never included in scheduled backups.
- **Privacy tools**: a data-shapes export that describes the structure of your data (no names, places, ids, dates or body measurements) so problems can be debugged without sharing your data.

## Coming next

1. AI distillation of your Library into short, cited, reviewable notes (needs an AI connection), and OCR / video transcripts in a heavier image
2. Heart-rate zones from your Garmin settings, a first training-load view, "rebuild from stored files"
3. More data sources (Strava, COROS) with de-duplication
4. Agent connectivity (REST + MCP) so any AI can read your data, then mobile layout and an installable web app

## Credits and sources

The app builds on published research, and it says so. Every method names its source (a clickable credit in the app), and the
**References** page and [docs/references.md](docs/references.md) list each one with the full citation, what the app uses it for,
its limits, and an honest label for how well it was checked (full text read, abstract only, or secondary sources).

## Docs

- [Install guide](docs/install.md) (Docker, Unraid, first run)
- [Roadmap](docs/roadmap.md) and [changelog](CHANGELOG.md)
- [Race predictions, max heart rate and VO2max: how they work](docs/predictions.md)
- [References and credits](docs/references.md)
- [Garmin Personal API](docs/garmin.md): key setup, token exchange, data coverage, terms notes
- [Ingest area](docs/ingest.md): tiers, retrieval order, tooling, templates

## License

[MIT](LICENSE)
