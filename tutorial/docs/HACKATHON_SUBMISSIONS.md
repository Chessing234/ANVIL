# Hackathon submission index

Each row links to a tailored **README**, **SUBMISSION**, and **demo video script** for that venue.
All packages live under `submissions/<slug>/`. Regenerate programmatically if needed:

```bash
python scripts/generate_submission_packages.py
```

| # | Slug | Theme |
| --- | --- | --- |
| 1 | `find_evil` | Autonomous IR, self-correction, accuracy reports |
| 2 | `splunk_agentic_ops` | Splunk MCP, SPL, observability + teaching |
| 3 | `uipath_agenthack` | Multi-agent orchestration / Maestro track |
| 4 | `dsh_hacks_v1` | STEM education, CSTA, sandbox learning |
| 5 | `usaii_global_ai` | Social impact, responsible AI literacy |
| 6 | `gitlab_transcend` | Secure development & DevSecOps education |
| 7 | `turing_test` | On-chain credentials & verifiable learning |
| 8 | `moonshot` | Moonshot paper + civilizational “protective education” framing |
| 9 | `aws_security_jam` | Cloud war-games & container deployment |
| 10 | `microsoft_defender_hack` | XDR-style Windows investigations |
| 11 | `elastic_agent_hack` | Observability-native detection + lessons |
| 12 | `snyk_devsecops` | DevSecOps + dependency-aware narratives |
| 13 | `tailscale_zero_trust` | Private mesh / zero-trust deployments |
| 14 | `fly_io_edge_deploy` | Edge-friendly compose & global demos |
| 15 | `hackforge_cyber` | Open engineering depth / build tracks |
| 16 | `mitre_attack_datathon` | ATT&CK-aligned investigations |
| 17 | `nvidia_ai_defense` | ONNX / GPU-ready edge hooks |
| 18 | `okta_identity_hack` | IAM-centric auth narratives |
| 19 | `lacework_cloud_sec` | CSPM-style cloud risk storytelling |
| 20 | `verizon_threat_hack` | Telco-scale DNS / exfiltration templates |

## Demo automation

Shell automation lives in `docs/demo_scripts/`:

- `find_evil_demo.sh` — incident → investigate → accuracy report
- `splunk_demo.sh` — same API path plus Splunk integration callouts
- `uipath_demo.sh` — queue-style orchestration narration + API demo
- `dsh_hacks_demo.sh` — education-focused polling for lessons + curriculum mapping
- `education_demo.sh` — student profile + lesson consumption path

Make them executable once:

```bash
chmod +x docs/demo_scripts/*.sh
```
