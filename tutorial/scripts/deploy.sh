#!/usr/bin/env bash
#
# Turnkey deploy for Project TUTORIAL.
#
#   ./scripts/deploy.sh            # local stack over HTTP (http://localhost)
#   ./scripts/deploy.sh prod       # production stack with automatic HTTPS (Caddy)
#
# What it does:
#   1. Ensures a Docker CLI is on PATH (adds Docker Desktop's bin on macOS).
#   2. Creates .env from .env.example on first run and generates a strong
#      TUTORIAL_API__DEMO_API_KEY. Existing .env files are never overwritten.
#   3. Builds images and starts the stack (base, or base + prod overlay).
#   4. Waits for the API healthcheck and prints the result.
#
# Production note: for HTTPS, export SITE_ADDRESS (your domain) before running
# `prod`, and make sure DNS points at this host with ports 80/443 reachable.

set -euo pipefail

MODE="${1:-local}"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# --- 1. Docker CLI -----------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
	if [ -d "/Applications/Docker.app/Contents/Resources/bin" ]; then
		export PATH="$PATH:/Applications/Docker.app/Contents/Resources/bin"
	fi
fi
command -v docker >/dev/null 2>&1 || die "docker CLI not found. Install Docker first."
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 not available."
docker info >/dev/null 2>&1 || die "Docker daemon is not running. Start Docker and retry."

# --- 2. Environment file -----------------------------------------------------
if [ ! -f .env ]; then
	[ -f .env.example ] || die ".env.example missing; cannot bootstrap .env."
	cp .env.example .env
	KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))' 2>/dev/null \
		|| head -c 32 /dev/urandom | base64 | tr -d '/+=' )"
	# Portable in-place edit (GNU and BSD sed).
	if sed --version >/dev/null 2>&1; then
		sed -i "s|^TUTORIAL_API__DEMO_API_KEY=.*|TUTORIAL_API__DEMO_API_KEY=${KEY}|" .env
	else
		sed -i '' "s|^TUTORIAL_API__DEMO_API_KEY=.*|TUTORIAL_API__DEMO_API_KEY=${KEY}|" .env
	fi
	log "Created .env with a freshly generated TUTORIAL_API__DEMO_API_KEY."
else
	log "Using existing .env (left untouched)."
	if grep -q '^TUTORIAL_API__DEMO_API_KEY=tutorial-demo-key$' .env; then
		warn "TUTORIAL_API__DEMO_API_KEY is still the demo default. Rotate it before exposing publicly."
	fi
	if grep -q '^TUTORIAL_LLM__API_KEY=replace-me$' .env; then
		warn "TUTORIAL_LLM__API_KEY is still 'replace-me'. Set a real key for live LLM behavior."
	fi
fi

# --- 3. Compose files --------------------------------------------------------
COMPOSE_FILES=(-f docker-compose.yml)
if [ "$MODE" = "prod" ]; then
	COMPOSE_FILES+=(-f docker-compose.prod.yml)
	log "Mode: production (Caddy automatic HTTPS)."
	if [ "${SITE_ADDRESS:-}" = "" ]; then
		warn "SITE_ADDRESS is unset; Caddy will serve plain HTTP on :80. Export your domain for TLS."
	else
		log "SITE_ADDRESS=${SITE_ADDRESS}"
	fi
elif [ "$MODE" = "local" ]; then
	log "Mode: local (HTTP on http://localhost)."
else
	die "Unknown mode '$MODE'. Use 'local' or 'prod'."
fi

# --- 4. Build, start, verify -------------------------------------------------
log "Building and starting containers..."
docker compose "${COMPOSE_FILES[@]}" up -d --build

log "Waiting for the API to become healthy..."
API_CID="$(docker compose "${COMPOSE_FILES[@]}" ps -q api)"
for _ in $(seq 1 40); do
	status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$API_CID" 2>/dev/null || echo starting)"
	[ "$status" = "healthy" ] && break
	sleep 3
done

if [ "${status:-}" = "healthy" ]; then
	log "API is healthy."
else
	docker compose "${COMPOSE_FILES[@]}" logs --tail 40 api || true
	die "API did not become healthy. See logs above."
fi

echo
log "Deploy complete."
docker compose "${COMPOSE_FILES[@]}" ps
echo
APIKEY="$(grep '^TUTORIAL_API__DEMO_API_KEY=' .env | cut -d= -f2-)"
if [ "$MODE" = "prod" ] && [ "${SITE_ADDRESS:-}" != "" ]; then
	echo "  UI:        https://${SITE_ADDRESS}"
else
	echo "  UI:        http://localhost"
	echo "  API:       http://127.0.0.1:8000"
fi
echo "  API key:   ${APIKEY}  (send as 'X-API-Key' header; stored in .env)"
