# Demo video script — `nvidia_ai_defense`

**Target length:** 3–5 minutes  
**Audience:** Technical judges + security educators

## Scene 1 — Problem (30–45s)

**Screen:** Title slide with `TUTORIAL-GPU: Accelerated Inference Hooks for Agentic Defense` and tagline.  
**Narration:** Briefly state the dual crisis: alert fatigue plus lack of realistic training data.

## Scene 2 — Architecture (45–60s)

**Screen:** `docs/ARCHITECTURE.md` opened to the mermaid diagram (or redrawn in slides).  
**Narration:** Walk API → coordinator → defense/teaching workflows → persistence. Mention MCP
integrations relevant to `nvidia_ai_defense`.

## Scene 3 — Live API (60–90s)

**Screen:** Terminal running `docker compose up -d`, then `curl` health check with
`X-API-Key: tutorial-demo-key`.  
**Narration:** Highlight health endpoint bypassing rate limits, JSON responses, and structured errors.

## Scene 4 — Incident + investigation (60–90s)

**Screen:** POST create incident, POST investigate, GET detail showing investigation steps and
at least one `is_self_correction` step.  
**Narration:** Tie each UI/API element to the hackathon angle: Edge optional dependency group for ONNXRuntime, ARM64 Dockerfile, and narrative agents that can consume quantized local models where GPUs exist.…

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
