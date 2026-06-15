# TUTORIAL Deployment Guide

Goal: a new engineer can run the full stack locally in about **10 minutes** with Docker, or wire the
same containers into a cloud environment.

## Prerequisites

- Docker 24+ with Compose v2 (`docker compose version`)
- Optional: Python 3.11 + Node 20 for native dev (see repository `Makefile`)
- 4 GB RAM minimum for compose (API + SPA build artifacts)

## Turnkey deploy (one command)

`scripts/deploy.sh` is the fastest path. It bootstraps `.env` with a **strong
random** `TUTORIAL_API__DEMO_API_KEY` on first run, builds the images, starts
the stack, and waits for the API healthcheck.

```bash
cd tutorial
./scripts/deploy.sh          # local stack over HTTP -> http://localhost
./scripts/deploy.sh prod     # production stack with automatic HTTPS (Caddy)
```

For `prod`, point DNS at the host and export your domain before running so Caddy
can provision TLS automatically:

```bash
export SITE_ADDRESS=tutorial.example.com
export TLS_EMAIL=ops@example.com   # optional
./scripts/deploy.sh prod
```

The script prints the API key (also stored in `.env`) on completion. It never
overwrites an existing `.env`, and warns if the demo key or `replace-me` LLM key
are still in place.

## Quick start (Docker Compose, manual)

```bash
cd tutorial
cp .env.example .env          # then edit secrets (see below)
docker compose up -d --build
curl -sS http://127.0.0.1:8000/api/v1/system/health
open http://localhost
```

- API: `http://127.0.0.1:8000`
- UI (nginx): `http://localhost` (proxies `/api/` to the API container)
- API key: value of `TUTORIAL_API__DEMO_API_KEY` in `.env` (sent as `X-API-Key`)

Compose loads `.env` automatically (`env_file`), and the frontend image is built
with the same `TUTORIAL_API__DEMO_API_KEY` so the SPA and API agree.

Data persists in the named volume `tutorial_data` mounted at `/app/data` inside the API container.

## Production stack with automatic HTTPS (`docker-compose.prod.yml`)

The production overlay adds a **Caddy** reverse proxy that terminates TLS and
auto-renews certificates, plus `restart: always` and JSON log rotation on every
service. Caddy owns ports 80/443; the frontend is no longer published directly.

```bash
export SITE_ADDRESS=tutorial.example.com
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Requires Docker Compose **v2.24+** (for the `!reset` ports tag). Certificate
state lives in the `caddy_data` volume — back it up to avoid re-issuance on
rebuilds.

## Environment variables (nested)

Settings use prefix `TUTORIAL_` and nested delimiter `__` (see `config/settings.py`). Common
overrides:

| Variable | Purpose |
| --- | --- |
| `TUTORIAL_DATABASE__URL` | e.g. `sqlite:///data/tutorial.db` or `postgresql+asyncpg://user:pass@host/db` |
| `TUTORIAL_API__DEMO_API_KEY` | Shared secret for `X-API-Key` |
| `TUTORIAL_API__EVIDENCE_UPLOAD_DIR` | Writable evidence directory |
| `TUTORIAL_ORCHESTRATION__PERSISTENCE_DB_PATH` | SQLite path for orchestration store |
| `TUTORIAL_ORCHESTRATION__DEFENSE_CHECKPOINT_DB` | Defense LangGraph checkpoints |
| `TUTORIAL_ORCHESTRATION__TEACHING_CHECKPOINT_DB` | Teaching LangGraph checkpoints |
| `TUTORIAL_MCP__SERVERS_JSON` | JSON array of MCP stdio servers |

> **Note:** The async message bus is **in-process**; there is no `REDIS_URL`-style setting. Redis may
> be added later for cross-host fan-out, but it is not required today.

## Edge / ARM64 (`docker-compose.edge.yml`)

```bash
docker compose -f docker-compose.edge.yml build
docker compose -f docker-compose.edge.yml up -d
```

`docker/Dockerfile.edge` targets `linux/arm64` and installs the optional `[edge]` Python extras.
Build this image on Apple Silicon natively, or enable QEMU/binfmt on amd64 CI.

## Agent container (`Dockerfile.agent`)

`python main.py --mode agent` starts the coordinator **without** HTTP. **Do not** run multiple agent
containers against the same SQLite files as the API—SQLite locking will corrupt state. For
horizontal scaling, move the primary database to PostgreSQL and redesign bus fan-out.

## Kubernetes (scale-out sketch)

1. Build and push images (see `.github/workflows/tutorial-docker-publish.yml` at the monorepo root).
2. Run API as a Deployment with persistent volumes for `/app/data` **or** external Postgres + RWX
   volumes for checkpoint sqlite (prefer single-writer StatefulSet for checkpoint files).
3. Expose ClusterIP Service port 8000; put nginx (or ingress) in front for TLS termination.
4. Run migrations / `python main.py --mode api --init-db` as a Job on upgrades.

## CI / GitHub Actions

- **Monorepo (`ANVIL/…`):** workflows live in `.github/workflows/tutorial-*.yml` and set
  `working-directory: tutorial`.
- **Standalone `tutorial/` repo:** workflows live in `tutorial/.github/workflows/` and assume the
  checkout root is this project (see `tutorial/.github/README.md`).

Local parity with CI:

```bash
make ci-local
```

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `401 Invalid or missing X-API-Key` | Export `X-API-Key` header matching settings. |
| Frontend cannot reach API | Ensure SPA was built with `VITE_API_URL=/api/v1` (Compose default) and nginx proxies `/api/`. |
| SQLite `database is locked` | Use a single API writer; migrate to Postgres for concurrent writers. |
| Healthcheck flapping | Increase `start_period`; first boot runs migrations and loads graphs. |
| WebSocket fails through proxy | Confirm `Upgrade` and `Connection` headers (see `docker/nginx.conf`). |

## Security checklist for production

- Rotate `TUTORIAL_API__DEMO_API_KEY` to a strong random value (`deploy.sh` does
  this automatically on first run).
- Terminate TLS at the edge. The `prod` overlay does this for you via Caddy;
  otherwise put nginx/an ingress/a load balancer in front.
- Restrict CORS: `TUTORIAL_API__CORS_ALLOW_ORIGINS` defaults to `["*"]`. Set it
  to your real origin(s), e.g. `TUTORIAL_API__CORS_ALLOW_ORIGINS=["https://tutorial.example.com"]`.
- Do not expose Postgres or checkpoint volumes publicly.
- Mount secrets via orchestrator secrets, not plaintext env files in images.

## GitHub Pages (`*.github.io`)

GitHub Pages only hosts the **static SPA**. The API must run elsewhere (Docker
on a VPS, tunnel, etc.). See [`GITHUB_PAGES.md`](./GITHUB_PAGES.md) and the
workflow `.github/workflows/tutorial-github-pages.yml` at the monorepo root.

**Render (free API):** see [`RENDER.md`](./RENDER.md) and root `render.yaml`.
