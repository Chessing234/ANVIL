# ANVIL — Project TUTORIAL

**ANVIL** is the repository codename for [**Project TUTORIAL**](tutorial/README.md): an autonomous multi-agent cybersecurity platform where **Defense Agents** investigate incidents and **Teaching Agents** convert operational artifacts into CSTA-aligned STEM lessons.

> *The World's First Agentic AI That Learns by Teaching.*

## Quick start (demo)

```bash
cd tutorial
docker compose up -d --build
```

| Service | URL |
|---------|-----|
| **Dashboard (SOC + Learn)** | http://localhost |
| **API** | http://localhost:8000/api/v1 |
| **API docs** | http://localhost:8000/docs |

Default API key: `tutorial-demo-key`

### Hero demo flow

1. Open **Incidents** → create or pick a seeded incident → **Investigate**
2. Open the **Investigation** view → self-correction log + accuracy report
3. Click **Open generated lesson** → play the auto-generated lesson from that incident
4. Open **Credentials** → see blockchain-style attestations from completed lessons

Automated script: `tutorial/docs/demo_scripts/find_evil_demo.sh`

## Repository layout

```
ANVIL/
├── render.yaml              # Render.com API blueprint
├── .github/workflows/       # CI, GitHub Pages, Docker publish
└── tutorial/                # ← all product code
    ├── api/                 # FastAPI REST + WebSocket
    ├── frontend/            # React SOC + education UI
    ├── orchestration/       # LangGraph defense + teaching workflows
    ├── agents/              # Rich agent modules
    ├── platforms/           # Splunk, UiPath, SIFT, blockchain, GitLab, edge
    ├── submissions/         # 20 hackathon venue packages
    └── docs/                # Architecture, deployment, demo scripts
```

## Hackathon submissions

Twenty venue-specific packages live under `tutorial/submissions/` with README, SUBMISSION.md, and demo video scripts. See [`tutorial/docs/HACKATHON_SUBMISSIONS.md`](tutorial/docs/HACKATHON_SUBMISSIONS.md).

## Development

```bash
cd tutorial
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
make run          # API + agents + seed
make test         # pytest suite
cd frontend && npm install && npm run dev
```

Set `TUTORIAL_LLM__API_KEY` in `.env` for LLM-generated lesson narratives.

## License

MIT — see [tutorial/README.md](tutorial/README.md).
