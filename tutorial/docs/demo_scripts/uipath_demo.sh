#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

export TUTORIAL_API_BASE="${TUTORIAL_API_BASE:-http://127.0.0.1:8000}"
export X_API_KEY="${X_API_KEY:-tutorial-demo-key}"

echo "=== TUTORIAL: UiPath / Maestro-style orchestration demo ==="
echo "Highlights queue-oriented agents under platforms/uipath when enterprise keys are present."

docker compose up -d --build

python3 - <<'PY'
import os
import time
import urllib.request

base = os.environ["TUTORIAL_API_BASE"].rstrip("/")
for _ in range(90):
    try:
        urllib.request.urlopen(f"{base}/api/v1/system/health", timeout=5)
        print("API healthy")
        raise SystemExit(0)
    except OSError:
        time.sleep(1)
raise SystemExit("API did not become healthy in time")
PY

RESP="$(curl -fsS -X POST "${TUTORIAL_API_BASE}/api/v1/incidents/" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${X_API_KEY}" \
  -d '{"title":"Cross-system fraud runbook","description":"Finance queue + SOC queue must converge on shared correlation ID.","severity":"high","status":"open","incident_type":"orchestration","tags":["uipath-demo"]}')"
ID="$(printf '%s' "$RESP" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")"
export INCIDENT_ID="$ID"

curl -fsS -X POST "${TUTORIAL_API_BASE}/api/v1/incidents/${INCIDENT_ID}/investigate" \
  -H "X-API-Key: ${X_API_KEY}" >/dev/null

python3 - <<'PY'
import json
import os
import time
import urllib.request

base = os.environ["TUTORIAL_API_BASE"].rstrip("/")
iid = os.environ["INCIDENT_ID"]
key = os.environ["X_API_KEY"]
for _ in range(120):
    req = urllib.request.Request(
        f"{base}/api/v1/incidents/{iid}",
        headers={"X-API-Key": key},
    )
    data = json.load(urllib.request.urlopen(req, timeout=30))
    if len(data.get("investigation_steps") or []) >= 3:
        print("Coordinator finished defense/teach handoff — Maestro-style story ready for video.")
        raise SystemExit(0)
    time.sleep(1)
raise SystemExit("timeout waiting for investigation steps")
PY

curl -fsS "${TUTORIAL_API_BASE}/api/v1/agents/" -H "X-API-Key: ${X_API_KEY}" | python3 -m json.tool
echo "Dashboard: http://localhost"
