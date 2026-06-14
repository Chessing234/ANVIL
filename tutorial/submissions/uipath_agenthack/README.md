# TUTORIAL-Orchestra: Multi-Agent Orchestration for Autonomous Security & Education

**Twenty agents, one mission: protect and educate.**

This folder is the `uipath_agenthack` hackathon submission slice for **Project TUTORIAL** — an agentic
security platform that learns by teaching. The running system, APIs, and Docker stack live at
the repository root; this directory only contains narrative and demo guidance tailored for
judges here.

## Why this hackathon

UiPath Maestro-style queue orchestration, dynamic task routing, and human-in-the-loop handoffs modeled after enterprise RPA control rooms — submit to Track 1 (Maestro Case).

## Quick links

- [SUBMISSION.md](./SUBMISSION.md) — full write-up for judges
- [demo_video_script.md](./demo_video_script.md) — 3–5 minute recording plan
- Repository docs: `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md`, `docs/API.md`

## One-command demo (API)

```bash
cd /path/to/tutorial
docker compose up -d --build
curl -s -H "X-API-Key: tutorial-demo-key" http://127.0.0.1:8000/api/v1/system/health
```

Open the dashboard at `http://localhost` after compose (nginx → API).
