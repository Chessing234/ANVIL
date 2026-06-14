# TUTORIAL HTTP API

The live OpenAPI document is generated from FastAPI and committed for offline review as
`docs/openapi.json`. Regenerate after router changes:

```bash
cd tutorial
pip install -e .
python scripts/export_openapi.py
```

Interactive docs: `http://127.0.0.1:8000/docs` (when the API is running).

## Base URL and version

- **Prefix:** `/api/v1`
- **Example local base:** `http://127.0.0.1:8000/api/v1`

## Authentication

All JSON routes except `GET /api/v1/system/health` expect header:

```http
X-API-Key: tutorial-demo-key
```

The default key comes from `TUTORIAL_API__DEMO_API_KEY` (see `config/settings.py`). Override in
production.

## Rate limiting

`RateLimitMiddleware` enforces `TUTORIAL_API__RATE_LIMIT_PER_MINUTE` (default 100) per client IP.
`/docs`, `/openapi.json`, `/redoc`, and `/api/v1/system/health` are exempt.

## Error shape

Structured errors return JSON:

```json
{
  "error": "http_error",
  "detail": "Incident not found",
  "timestamp": "2026-06-11T12:00:00+00:00"
}
```

Common HTTP statuses: `400` validation, `401` missing/invalid API key, `404` missing entities,
`429` rate limit, `500` unhandled server faults.

## Core endpoints (summary)

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/system/health` | Liveness + DB ping + coordinator flag (no API key). |
| GET | `/system/flywheel` | Knowledge graph stats. |
| POST | `/incidents/` | Create incident. |
| GET | `/incidents/` | List incidents with optional filters. |
| GET | `/incidents/{id}` | Detail with investigation steps, evidence, lessons. |
| POST | `/incidents/{id}/investigate` | Run defense + teaching persistence pipeline. |
| GET | `/incidents/{id}/accuracy-report` | FIND EVIL! style accuracy JSON. |
| POST | `/incidents/{id}/evidence` | Multipart evidence upload. |
| GET | `/investigations/{id}/chain-of-custody` | Custody chains. |
| GET | `/lessons/{id}` | Full lesson narrative + interactives. |
| GET | `/lessons/{id}/curriculum-mapping` | CSTA mapping payload. |
| WS | `/ws/events` | Live events (`api_key` query param). |

## Example: create and investigate

```bash
export KEY=tutorial-demo-key
export BASE=http://127.0.0.1:8000/api/v1

curl -sS -H "X-API-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"title":"DNS spike","description":"NXDOMAIN storm from single host.","severity":"high","status":"open","incident_type":"dns"}' \
  "$BASE/incidents/" | tee /tmp/inc.json

IID=$(python3 -c "import json; print(json.load(open('/tmp/inc.json'))['id'])")

curl -sS -X POST -H "X-API-Key: $KEY" "$BASE/incidents/$IID/investigate"

curl -sS -H "X-API-Key: $KEY" "$BASE/incidents/$IID" | python3 -m json.tool
```

## WebSocket

`GET ws://host/api/v1/ws/events?api_key=tutorial-demo-key` mirrors the HTTP API key. When the SPA
uses a relative API base (`/api/v1`), browsers derive `ws(s)://` from the page origin automatically
(`frontend/src/api/websocket.ts`).

## OpenAPI artifact

See `docs/openapi.json` for the full schema: components, enums, and nested DTOs exactly as served
by FastAPI.
