# ai-endurance-coach

Self-hosted, AI-optional endurance training dashboard: Garmin sync, run analysis and a literature ingest area, in a single Docker container.

> **Status: pre-alpha, v0.1 skeleton.** First-run setup, login, encrypted Garmin key and Garmin activity sync work; dashboard charts and maps are next. See the [roadmap](docs/roadmap.md) and [install guide](docs/install.md). Default port: **26219**.

## Disclaimer: vibe-coded, use at your own risk

This project was largely written with AI assistance ("vibe-coded") and has not had a professional security or safety review. It is provided **as is**, with no warranty (see the [MIT license](LICENSE)).

- **Digital risk:** it handles your Garmin API key and personal health data. Bugs, misconfiguration or exposing it to the internet could leak or lose that data. Keep it on a trusted network or behind a VPN/authenticating proxy, use HTTPS if exposed, back up your data volume, and revoke your Garmin key if in doubt.
- **Physical risk:** training metrics, plans or AI-generated suggestions may be wrong. This is not medical advice and is not a substitute for a qualified coach or doctor. Do not push through pain, illness or injury because a dashboard said so. You are responsible for your own training decisions.
- **Garmin terms:** use only your own data with your own key, and read Garmin's terms yourself.

## Principles

- **Self-contained, AI-optional.** One Docker container. Sync, storage, dashboard and ingest all work with no AI.
- **Bring your own agent.** The same data and ingest area will be exposed through a REST API and an MCP server, so you can connect a local model, Claude, ChatGPT, Codex or anything else (roadmap v0.5).
- **Public code, private data.** Your Garmin key, health data and ingested files stay on the server running your container, on a mounted volume. They are never in this repo (see `.gitignore`).
- **Your own data only.** Garmin's Personal API is licensed for personal use with your own data. Each user runs their own instance with their own key.

## Planned features

1. Garmin data sync (activities incl. per-second samples, sleep, HRV, Body Battery, stress)
2. Dashboard: recent mileage, single-run detail with map
3. Ingest area for studies, videos and articles, kept in three forms: actionable summary, full-text Markdown, original source
4. Recovery views
5. Agent connectivity (REST + MCP)

## Docs

- [Install guide](docs/install.md) (Docker, Unraid, first run)
- [Roadmap](docs/roadmap.md)
- [Garmin Personal API](docs/garmin.md): key setup, token exchange, data coverage, terms notes
- [Ingest area](docs/ingest.md): tiers, retrieval order, tooling, templates

## License

[MIT](LICENSE)
