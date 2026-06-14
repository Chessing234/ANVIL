#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

export TUTORIAL_API_BASE="${TUTORIAL_API_BASE:-http://127.0.0.1:8000}"
export X_API_KEY="${X_API_KEY:-tutorial-demo-key}"

echo "=== TUTORIAL: DSH Hacks (STEM + sandbox) Demo ==="

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
  -d '{"title":"Classroom ransomware tabletop","description":"Students walk through encrypted shares and recovery steps.","severity":"medium","status":"open","incident_type":"education","tags":["dsh-hacks"]}')"
ID="$(printf '%s' "$RESP" | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")"
export INCIDENT_ID="$ID"

LESSON_FILE="$(mktemp)"
export LESSON_FILE

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
path = os.environ["LESSON_FILE"]
for _ in range(120):
    req = urllib.request.Request(
        f"{base}/api/v1/incidents/{iid}",
        headers={"X-API-Key": key},
    )
    data = json.load(urllib.request.urlopen(req, timeout=30))
    lessons = data.get("lessons") or []
    if lessons:
        lid = lessons[0]["id"]
        print(f"Lesson available: {lid}")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(lid)
        raise SystemExit(0)
    time.sleep(1)
raise SystemExit("timeout waiting for lessons")
PY

LESSON_ID="$(cat "$LESSON_FILE")"
rm -f "$LESSON_FILE"
curl -fsS "${TUTORIAL_API_BASE}/api/v1/lessons/${LESSON_ID}/curriculum-mapping" \
  -H "X-API-Key: ${X_API_KEY}" | python3 -m json.tool

echo "Open Learn + Sandbox tabs in the SPA. Dashboard: http://localhost"
