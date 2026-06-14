# Project TUTORIAL

Autonomous multi-agent system where **Defense Agents** handle real cybersecurity incidents and **Teaching Agents** convert operational actions into personalized interactive STEM lessons.

This repository contains the foundational scaffold: configuration, structured logging, shared models, an async in-memory message bus, agent base classes, LangGraph-compatible state machines with SQLite checkpointing, and Docker tooling.

## Quick start

```bash
cd tutorial
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
pytest
```

## Configuration

All settings load from environment variables with the `TUTORIAL_` prefix and nested keys using `__` (for example `TUTORIAL_LLM__MODEL_NAME`). See `.env.example` for the full surface.

## Architecture

- **`config/`** — Pydantic settings, constants, and structlog YAML wiring.
- **`core/`** — Message bus, `BaseAgent`, state machine, exceptions.
- **`shared/`** — Cross-cutting Pydantic models, types, and async utilities.

## Docker

```bash
docker compose build
docker compose up
```

The default compose file runs the application image with optional Redis for future horizontal scaling and a volume for evidence storage.

## GitHub Pages (static UI)

To publish the dashboard to **`https://<user>.github.io/<repo>/`**, enable Pages
(GitHub Actions), set the repository variable `TUTORIAL_PAGES_API_URL` to your
live HTTPS API, then run the **Tutorial — GitHub Pages** workflow. Full steps:
[`docs/GITHUB_PAGES.md`](docs/GITHUB_PAGES.md).

## License

MIT
