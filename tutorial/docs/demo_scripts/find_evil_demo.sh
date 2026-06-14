#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

export TUTORIAL_API_BASE="${TUTORIAL_API_BASE:-http://127.0.0.1:8000}"
export X_API_KEY="${X_API_KEY:-tutorial-demo-key}"

echo "=== TUTORIAL: FIND EVIL! Demo ==="

echo "1) Starting stack (api + frontend)..."
docker compose up -d --build

echo "2) Waiting for API health..."
python3 - <<'PY'
import os
import time
import urllib.error
import urllib.request

base = os.environ["TUTORIAL_API_BASE"].rstrip("/")
for _ in range(90):
    try:
        urllib.request.urlopen(f"{base}/api/v1/system/health", timeout=5)
        print("   API healthy")
        raise SystemExit(0)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        time.sleep(1)
raise SystemExit("API did not become healthy in time")
PY

echo "3) Submitting incident..."
RESP="$(curl -fsS -X POST "${TUTORIAL_API_BASE}/api/v1/incidents/" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${X_API_KEY}" \
  -d '{"title":"Suspicious DNS Traffic","description":"Spike in encrypted DNS queries to a rare TLD with NXDOMAIN follow-on.","severity":"high","status":"open","incident_type":"dns","source_ip":"198.51.100.10","tags":["find-evil-demo"]}')"
ID="$(printf '%s' "$RESP" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")"
export INCIDENT_ID="$ID"
echo "   incident_id=${INCIDENT_ID}"

echo "4) Starting investigation..."
curl -fsS -X POST "${TUTORIAL_API_BASE}/api/v1/incidents/${INCIDENT_ID}/investigate" \
  -H "X-API-Key: ${X_API_KEY}" >/dev/null

echo "5) Waiting for investigation artifacts..."
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
    steps = data.get("investigation_steps") or []
    if len(steps) >= 3:
        print(f"   investigation_steps={len(steps)}")
        raise SystemExit(0)
    time.sleep(1)
raise SystemExit("timeout waiting for investigation steps")
PY

echo "6) Accuracy report..."
curl -fsS "${TUTORIAL_API_BASE}/api/v1/incidents/${INCIDENT_ID}/accuracy-report" \
  -H "X-API-Key: ${X_API_KEY}" | python3 -m json.tool

echo "Demo complete. Dashboard: http://localhost"
