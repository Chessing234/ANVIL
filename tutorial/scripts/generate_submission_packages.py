#!/usr/bin/env python3
"""Generate tailored hackathon submission markdown packages under submissions/."""

from __future__ import annotations

import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "submissions"

PACKAGES: list[dict[str, str]] = [
    {
        "slug": "find_evil",
        "title": "TUTORIAL-IR: Autonomous Incident Response with Self-Correcting Narrative Intelligence",
        "tagline": "An AI agent that investigates security incidents like a senior analyst — and corrects itself when wrong.",
        "angle": (
            "FIND EVIL! alignment: autonomous investigation timelines, explicit self-correction steps, "
            "SIFT-ready evidence paths, and a published accuracy report per incident."
        ),
    },
    {
        "slug": "splunk_agentic_ops",
        "title": "TUTORIAL-Ops: Agentic Security Operations with a Real-Time STEM Education Pipeline",
        "tagline": "Turn every security alert into a learning opportunity.",
        "angle": (
            "Splunk MCP integration, SPL generation with validation, threat-hunt templates, and live "
            "observability hooks that narrate operator actions into teachable moments."
        ),
    },
    {
        "slug": "uipath_agenthack",
        "title": "TUTORIAL-Orchestra: Multi-Agent Orchestration for Autonomous Security & Education",
        "tagline": "Twenty agents, one mission: protect and educate.",
        "angle": (
            "UiPath Maestro-style queue orchestration, dynamic task routing, and human-in-the-loop "
            "handoffs modeled after enterprise RPA control rooms — submit to Track 1 (Maestro Case)."
        ),
    },
    {
        "slug": "dsh_hacks_v1",
        "title": "TUTORIAL-EDU: Turning Real Cyber Attacks Into Interactive CS Curriculum",
        "tagline": "Real incidents. Interactive lessons. Real skills.",
        "angle": (
            "STEM-first pedagogy: sandbox terminals, CSTA mapping endpoints, difficulty-aware narratives, "
            "and measurable learning outcomes tied to each incident."
        ),
    },
    {
        "slug": "usaii_global_ai",
        "title": "TUTORIAL-Good: AI That Protects Communities While Building Cyber Literacy",
        "tagline": "Closing the cybersecurity skills gap, one incident at a time.",
        "angle": (
            "Responsible AI guardrails, transparent investigation steps, and public-interest framing: "
            "defenders learn while organizations improve resilience."
        ),
    },
    {
        "slug": "gitlab_transcend",
        "title": "TUTORIAL-Dev: AI Agents for Secure Development & Developer Education",
        "tagline": "Every commit is a learning opportunity.",
        "angle": (
            "Secure SDLC storytelling: investigations that reference dependency risk, CI/CD hygiene, "
            "and merge-request friendly exports for GitLab-based review workflows."
        ),
    },
    {
        "slug": "turing_test",
        "title": "TUTORIAL-Chain: On-Chain Agent Identity for Decentralized Cybersecurity Education",
        "tagline": "Trustless security, verifiable learning.",
        "angle": (
            "Verifiable credential NFT flows, wallet-linked student profiles, and tamper-evident "
            "lesson attestations suitable for DeFi-adjacent education pilots."
        ),
    },
    {
        "slug": "moonshot",
        "title": "TUTORIAL-Moonshot: Protective Education as Civilizational Infrastructure",
        "tagline": "When defense and teaching share one nervous system, societies become antifragile.",
        "angle": (
            "First-principles argument for coupling incident response with pedagogy; includes required "
            "Moonshot paper (MOONSHOT_PAPER.md) on protective education as a new primitive."
        ),
    },
    {
        "slug": "aws_security_jam",
        "title": "TUTORIAL-AWS: Incident War-Games with Agentic Runbooks",
        "tagline": "Simulate cloud-scale attacks; graduate analysts with receipts.",
        "angle": (
            "Containerized deployment on AWS Graviton-ready images, least-privilege API keys, "
            "and CloudWatch-friendly structured logs from structlog."
        ),
    },
    {
        "slug": "microsoft_defender_hack",
        "title": "TUTORIAL-Defender: XDR Narratives That Teach While They Hunt",
        "tagline": "From alert triage to micro-lessons without context switching.",
        "angle": (
            "Windows-centric investigation heuristics, host isolation simulations, and lesson cards "
            "that mirror Defender incident queues."
        ),
    },
    {
        "slug": "elastic_agent_hack",
        "title": "TUTORIAL-Elastic: Agentic Detection Engineering with Explainable Lessons",
        "tagline": "Every detection gap becomes a curriculum module.",
        "angle": (
            "JSON evidence chains, timeline exports compatible with SIEM analysts, and Elasticsearch-"
            "style aggregations in narrative copy for observability-native teams."
        ),
    },
    {
        "slug": "snyk_devsecops",
        "title": "TUTORIAL-SecureCode: DevSecOps Agents That Teach While They Fix",
        "tagline": "Shift-left security with shift-left literacy.",
        "angle": (
            "Supply-chain aware investigations, dependency metadata in evidence objects, and developer-"
            "first remediation narratives suitable for DevSecOps dashboards."
        ),
    },
    {
        "slug": "tailscale_zero_trust",
        "title": "TUTORIAL-Mesh: Zero-Trust Investigations Across Ephemeral Environments",
        "tagline": "Private by design, instructive by default.",
        "angle": (
            "Edge compose profiles, private networking assumptions, and operator guidance for running "
            "behind identity-aware proxies without exposing student data."
        ),
    },
    {
        "slug": "fly_io_edge_deploy",
        "title": "TUTORIAL-Fly: Global Edge Demos for Classroom-Scale SOC",
        "tagline": "Spin up a SOC in minutes, teach in seconds.",
        "angle": (
            "Single-command Docker Compose, health-checked API, and static SPA suitable for Fly Machines "
            "or any container edge with persistent volumes for SQLite workloads."
        ),
    },
    {
        "slug": "hackforge_cyber",
        "title": "TUTORIAL-Forge: Build-Your-Own Agent Lab for Blue Teams",
        "tagline": "Hack, break, replay, learn.",
        "angle": (
            "Open codebase, reproducible demos, and modular agents (defense, teaching, integrations) "
            "ideal for competitive build tracks focused on engineering depth."
        ),
    },
    {
        "slug": "mitre_attack_datathon",
        "title": "TUTORIAL-MITRE: ATT&CK-Tied Investigations with Pedagogy",
        "tagline": "Map tactics, teach techniques.",
        "angle": (
            "Explicit tactic/technique language in investigation steps, exportable timelines, and "
            "lesson linkages that reinforce ATT&CK literacy for collegiate competitors."
        ),
    },
    {
        "slug": "nvidia_ai_defense",
        "title": "TUTORIAL-GPU: Accelerated Inference Hooks for Agentic Defense",
        "tagline": "Optional ONNX path for edge and classroom inference.",
        "angle": (
            "Edge optional dependency group for ONNXRuntime, ARM64 Dockerfile, and narrative agents "
            "that can consume quantized local models where GPUs exist."
        ),
    },
    {
        "slug": "okta_identity_hack",
        "title": "TUTORIAL-Identity: Investigation Narratives Grounded in Auth Signals",
        "tagline": "Who did what, when, and why it matters for IAM teams.",
        "angle": (
            "Login failure heuristics, session risk storytelling, and student profiles that respect "
            "API-key authentication patterns common in enterprise pilots."
        ),
    },
    {
        "slug": "lacework_cloud_sec",
        "title": "TUTORIAL-Cloud: Agentic Cloud Security Posture with Teach-Back",
        "tagline": "Misconfigurations explained, not just flagged.",
        "angle": (
            "Cloud-native vocabulary in lessons, network exfiltration heuristics, and evidence objects "
            "that mirror CSPM alert schemas for practitioner judges."
        ),
    },
    {
        "slug": "verizon_threat_hack",
        "title": "TUTORIAL-Telco: Carrier-Scale Threat Narratives for Analyst Pipelines",
        "tagline": "DNS anomalies, lateral movement, and lessons that scale.",
        "angle": (
            "DNS tunneling templates in SPL heuristics, high-throughput JSON APIs, and rate-limited "
            "public endpoints suitable for telco SOC modernization pitches."
        ),
    },
]


def readme(slug: str, title: str, tagline: str, angle: str) -> str:
    return textwrap.dedent(
        f"""\
        # {title}

        **{tagline}**

        This folder is the `{slug}` hackathon submission slice for **Project TUTORIAL** — an agentic
        security platform that learns by teaching. The running system, APIs, and Docker stack live at
        the repository root; this directory only contains narrative and demo guidance tailored for
        judges here.

        ## Why this hackathon

        {angle}

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
        """
    )


def submission_md(meta: dict[str, str]) -> str:
    slug = meta["slug"]
    return textwrap.dedent(
        f"""\
        # {meta["title"]}

        **Tagline:** {meta["tagline"]}

        ## Problem

        Security teams drown in alerts while new analysts lack realistic, safe rehearsal environments.
        Universities and nonprofits cannot afford bespoke SOC simulators. The result: slower response,
        opaque investigations, and a widening cyber skills gap.

        ## Solution

        **Project TUTORIAL** couples LangGraph-powered defense workflows with a teaching pipeline that
        turns every resolved incident into CSTA-aligned lessons, interactive elements, and optional
        verifiable credentials. Operators get structured timelines with explicit self-correction;
        students get narratives grounded in the same evidence professionals saw.

        ## Hackathon angle: `{slug}`

        {meta["angle"]}

        ## Key features

        - FastAPI surface with `/api/v1/incidents`, investigations, lessons, students, knowledge graph,
          and WebSocket fan-out for live dashboards.
        - SQLite-first persistence with optional PostgreSQL for scale (see `docs/DEPLOYMENT.md`).
        - MCP registry for Splunk, security tools, LLM, and partner integrations.
        - Accuracy report endpoint per incident for FIND EVIL!-style scoring narratives.
        - Docker Compose stack with health-checked API and nginx-served React SPA.

        ## Technology stack

        | Layer | Choice |
        | --- | --- |
        | API | FastAPI, Uvicorn, Pydantic v2 |
        | Agents | LangGraph, structlog, asyncio |
        | Persistence | SQLAlchemy 2 async, SQLite / Postgres |
        | Frontend | React, Vite, TypeScript, Tailwind |
        | Ops | Docker multi-stage images, GitHub Actions CI |

        ## Architecture (conceptual)

        ```mermaid
        flowchart LR
          UI[React SPA] -->|HTTPS /api| API[FastAPI]
          API --> DB[(SQLite/Postgres)]
          API --> C[TutorialCoordinator]
          C --> D[DefenseWorkflow]
          C --> T[TeachingWorkflow]
          D --> M[MessageBus]
          T --> M
          C --> K[KnowledgeFlywheel]
        ```

        ## Demo instructions

        1. `docker compose up -d --build` from the `tutorial/` directory.
        2. `curl -H "X-API-Key: tutorial-demo-key" http://127.0.0.1:8000/api/v1/system/health`
        3. POST `/api/v1/incidents/` with JSON body (see `docs/demo_scripts/find_evil_demo.sh`).
        4. POST `/api/v1/incidents/{{id}}/investigate` then poll GET `/api/v1/incidents/{{id}}`.
        5. Open `http://localhost` for the UI; Settings lets you override API base and key.

        ## Team

        Populate this section in the hackathon portal with your roster (names, roles, emails, and
        links to LinkedIn or GitHub). Keep this repository copy synchronized with whatever you submit
        officially so judges can verify authorship.

        ## Roadmap

        - Postgres-backed horizontal scaling for coordinator pools.
        - Federated MCP credential vaults for multi-tenant SOC providers.
        - Expanded ONNX lesson recommenders on ARM classroom kits.
        """
    )


def demo_video_script(meta: dict[str, str]) -> str:
    return textwrap.dedent(
        f"""\
        # Demo video script — `{meta["slug"]}`

        **Target length:** 3–5 minutes  
        **Audience:** Technical judges + security educators

        ## Scene 1 — Problem (30–45s)

        **Screen:** Title slide with `{meta["title"]}` and tagline.  
        **Narration:** Briefly state the dual crisis: alert fatigue plus lack of realistic training data.

        ## Scene 2 — Architecture (45–60s)

        **Screen:** `docs/ARCHITECTURE.md` opened to the mermaid diagram (or redrawn in slides).  
        **Narration:** Walk API → coordinator → defense/teaching workflows → persistence. Mention MCP
        integrations relevant to `{meta["slug"]}`.

        ## Scene 3 — Live API (60–90s)

        **Screen:** Terminal running `docker compose up -d`, then `curl` health check with
        `X-API-Key: tutorial-demo-key`.  
        **Narration:** Highlight health endpoint bypassing rate limits, JSON responses, and structured errors.

        ## Scene 4 — Incident + investigation (60–90s)

        **Screen:** POST create incident, POST investigate, GET detail showing investigation steps and
        at least one `is_self_correction` step.  
        **Narration:** Tie each UI/API element to the hackathon angle: {meta["angle"][:200]}…

        ## Scene 5 — Dashboard + lesson (45–75s)

        **Screen:** Browser at `http://localhost` — Incidents list → Investigation timeline → Learn tab.  
        **Narration:** Show how the same evidence powers operator triage and student learning.

        ## Scene 6 — Close (20–30s)

        **Screen:** Accuracy report JSON or README quote.  
        **Narration:** Restate measurable impact and call to action (repo link, license, contact).

        ## Capture tips

        - Record 1080p terminal with font size ≥14pt.
        - Use clean browser profile; blur secrets if you override API keys on camera.
        - Keep audio mono-compatible; avoid copyrighted background music.
        """
    )


def moonshot_paper() -> str:
    return textwrap.dedent(
        """\
        # Protective Education: A Moonshot Paper for Project TUTORIAL

        ## Problem

        Civilization depends on digital infrastructure, yet two failures repeat: (1) defenders lack
        realistic rehearsal environments with faithful evidence chains, and (2) learners rarely train
        on incidents that are simultaneously authentic and ethically contained. Traditional cyber ranges
        are expensive; canned labs lack narrative depth; SOC tooling rarely teaches.

        ## First-principles insight

        **Investigation and pedagogy should share one state machine.** If the artifacts produced while
        securing an organization (timelines, evidence, corrections) are already structured, they can be
        losslessly transformed into lessons without synthetic “toy” data. The marginal cost of teaching
        drops toward zero as incident volume grows.

        ## Architecture

        TUTORIAL binds a `TutorialCoordinator` to LangGraph defense and teaching workflows. Defense
        checkpoints capture analyst-grade reasoning; teaching checkpoints emit CSTA-mapped narratives,
        interactive elements, and optional on-chain credentials. A knowledge flywheel graph connects
        concepts across incidents so communities compound literacy instead of resetting per course.

        ## Implications

        - **For enterprises:** Every investigation amortizes training spend; auditors gain explainable AI
          traces with explicit self-correction markers.
        - **For education:** Students practice on incidents that actually happened (redacted), not
          fabricated puzzles misaligned with employer stacks.
        - **For society:** “Protective education” becomes a primitive: systems that defend you while
          increasing your agency, not opaque models that replace you.

        ## Future work

        Federated lesson sharing across institutions, privacy-preserving aggregation of accuracy metrics,
        and hardware-backed student identities. The moonshot is not a single model — it is an
        operational pattern: **defense outputs are curriculum inputs, by construction.**
        """
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for meta in PACKAGES:
        d = OUT / meta["slug"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "README.md").write_text(
            readme(meta["slug"], meta["title"], meta["tagline"], meta["angle"]),
            encoding="utf-8",
        )
        (d / "SUBMISSION.md").write_text(submission_md(meta), encoding="utf-8")
        (d / "demo_video_script.md").write_text(demo_video_script(meta), encoding="utf-8")
        if meta["slug"] == "moonshot":
            (d / "MOONSHOT_PAPER.md").write_text(moonshot_paper(), encoding="utf-8")
    print(f"wrote {len(PACKAGES)} packages under {OUT}")


if __name__ == "__main__":
    main()
