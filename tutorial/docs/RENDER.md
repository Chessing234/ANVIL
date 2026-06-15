# Deploy the API on Render (free Web Service)

This repo includes a **`render.yaml`** [Blueprint](https://render.com/docs/infrastructure-as-code)
that builds `tutorial/docker/Dockerfile.api` and runs the FastAPI app.

## One-time setup (Dashboard)

1. Open [Render Dashboard](https://dashboard.render.com) → your workspace.
2. **Blueprints** → **New Blueprint Instance**.
3. Connect **GitHub** → select repo **`Chessing234/ANVIL`** (or your fork; if you fork,
   change the `repo:` URL in `render.yaml` first).
4. Confirm branch **`main`** and apply the Blueprint (creates **`tutorial-api`**).

Wait for the first deploy to go **Live**. Open the service → **URL** (ends in
`.onrender.com`).

## Secrets you should set in Render

| Variable | When |
| --- | --- |
| `TUTORIAL_LLM__API_KEY` | Required for real LLM calls (Blueprint uses `sync: false` so Render prompts you). |

`TUTORIAL_API__DEMO_API_KEY` is **auto-generated** (`generateValue: true`). Copy it
from **Environment** after deploy — you need the same value for GitHub Pages
(see below).

## CORS

The Blueprint sets:

`TUTORIAL_API__CORS_ALLOW_ORIGINS=["https://chessing234.github.io"]`

If your GitHub Pages URL or fork username differs, edit `render.yaml` (or
override in the Render dashboard) so the origin matches exactly what the
browser sends in the `Origin` header.

## Wire GitHub Pages to Render

From `tutorial/` on your laptop (requires [GitHub CLI](https://cli.github.com/)):

```bash
./scripts/gh-wire-pages-api.sh 'https://YOUR-SERVICE.onrender.com/api/v1' 'PASTE_TUTORIAL_API__DEMO_API_KEY'
```

Rebuild Pages after any change to `VITE_*` or the API URL.

## Free tier limitations

Ephemeral filesystem, spin-down after inactivity, cold starts — see
[Render: Deploy for Free](https://render.com/docs/free). Use Postgres + disk on
paid tiers when you outgrow the demo.

## CLI

Validate the Blueprint locally:

```bash
render blueprints validate render.yaml
```

Trigger a redeploy of an **existing** service:

```bash
render deploys create srv-XXXXXXXX --confirm
```

Creating the service the first time is done through the **Blueprint** flow above
(or the Render REST API with `RENDER_API_KEY`).
