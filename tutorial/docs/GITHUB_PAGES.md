# Deploy the TUTORIAL UI to GitHub Pages (`*.github.io`)

GitHub Pages serves **static files only**. The FastAPI backend **cannot** run on
`github.io`. This workflow publishes the **Vite/React dashboard**; it must talk
to an API you host elsewhere (Docker on a VPS, Fly.io, Railway, Cloudflare
Tunnel, etc.) over **HTTPS**.

## One-time repository setup

1. **Enable GitHub Pages from Actions**

   GitHub → your repository → **Settings** → **Pages** → **Build and
   deployment** → Source: **GitHub Actions**.

2. **Point the SPA at your live API**

   **Settings** → **Secrets and variables** → **Actions** → **Variables** →
   **New repository variable**:

   | Name | Example value |
   | --- | --- |
   | `TUTORIAL_PAGES_API_URL` | `https://api.yourdomain.com/api/v1` |

   Optional **Secret** (same screen, **Secrets** tab):

   | Name | Purpose |
   | --- | --- |
   | `TUTORIAL_PAGES_API_KEY` | Baked into the static build as `VITE_API_KEY`. Omit if users will paste a key in **Settings** inside the app (still stored in the browser only). |

   Use an **absolute** `https://…` URL. Relative `/api/v1` only works when the
   API is on the **same origin** as the site (not the case for `github.io`).

3. **CORS on the API**

   Set `TUTORIAL_API__CORS_ALLOW_ORIGINS` on the API host to include your Pages
   origin, for example:

   - User site (`username.github.io` repo): `["https://username.github.io"]`
   - Project site: `["https://username.github.io/repo-name"]`

   JSON array format matches `config/settings.py`.

4. **Merge to `main` (or `master`)** or run the workflow manually:

   **Actions** → **Tutorial — GitHub Pages** → **Run workflow**.

## URLs

- **Project repository** `github.com/you/ANVIL` → site is typically  
  `https://you.github.io/ANVIL/` (base path is computed automatically).
- **`username.github.io` repository** (user/org site) →  
  `https://username.github.io/` (base `/`).

The workflow copies `index.html` to `404.html` so client-side routes work when
you refresh a deep link.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Blank page or 404 on assets | Confirm Pages URL matches the computed base (project vs user site). |
| API calls fail (CORS) | Add your exact `https://…github.io…` origin to `TUTORIAL_API__CORS_ALLOW_ORIGINS`. |
| Mixed content errors | Pages is HTTPS; API URL must be `https://`, not `http://`. |
| WebSockets fail | API must support `wss://` on the same host as your API URL; ensure reverse proxy forwards WebSocket upgrade headers. |

## Related

- Full stack with Docker: `docs/DEPLOYMENT.md`
- Workflow file: `.github/workflows/tutorial-github-pages.yml`
