#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

export TUTORIAL_API_BASE="${TUTORIAL_API_BASE:-http://127.0.0.1:8000}"
export X_API_KEY="${X_API_KEY:-tutorial-demo-key}"

echo "=== TUTORIAL: Education-first demo ==="

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

curl -fsS "${TUTORIAL_API_BASE}/api/v1/knowledge/graph" -H "X-API-Key: ${X_API_KEY}" | python3 -m json.tool

RESP="$(curl -fsS -X POST "${TUTORIAL_API_BASE}/api/v1/incidents/" \
  -H "Content-Type: application/json" \
  -H "X-API-Key: ${X_API_KEY}" \
  -d '{"title":"Student SOC lab","description":"Guided narrative with checkpoints for beginners.","severity":"low","status":"open","incident_type":"education","tags":["education-demo"]}')"
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
    lessons = data.get("lessons") or []
    if lessons:
        lid = lessons[0]["id"]
        print(f"Primary lesson id: {lid}")
        mapping = json.load(
            urllib.request.urlopen(
                urllib.request.Request(
                    f"{base}/api/v1/lessons/{lid}/curriculum-mapping",
                    headers={"X-API-Key": key},
                ),
                timeout=30,
            )
        )
        print(json.dumps({"lesson_id": lid, "standards": mapping.get("standards_covered", [])}, indent=2))
        raise SystemExit(0)
    time.sleep(1)
raise SystemExit("timeout waiting for lessons")
PY

echo "Dashboard: http://localhost — visit Learn, Sandbox, and Profile."
