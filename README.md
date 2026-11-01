# ai-endurance-coach

Self-hosted, AI-optional endurance training dashboard: Garmin sync, run analysis and a literature ingest area, in a single Docker container.

> **Status: pre-alpha, planning.** Nothing is built yet. See the [roadmap](docs/roadmap.md).

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

- [Roadmap](docs/roadmap.md)
- [Garmin Personal API](docs/garmin.md): key setup, token exchange, data coverage, terms notes
- [Ingest area](docs/ingest.md): tiers, retrieval order, tooling, templates

## License

[MIT](LICENSE)
