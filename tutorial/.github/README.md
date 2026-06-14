# GitHub Actions (tutorial repo root)

These workflows assume **this `tutorial/` directory is the git repository root** (standalone clone).

If you keep TUTORIAL inside a monorepo (for example `ANVIL/tutorial/`), GitHub will not load this folder’s workflows. Use the parent repository’s `.github/workflows/tutorial-*.yml` files instead—they run with `working-directory: tutorial`.

| File | Purpose |
| --- | --- |
| `ci.yml` / `cd.yml` / `docker-publish.yml` | Standalone CI/CD |
| `github-pages.yml` | Build `frontend/` and deploy to GitHub Pages (this repo as root only) |
