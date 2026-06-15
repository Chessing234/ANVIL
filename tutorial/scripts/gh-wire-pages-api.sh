#!/usr/bin/env bash
# Wire the GitHub Pages build to your live API using gh, then redeploy the site.
#
# Usage (after your API is reachable over HTTPS):
#   ./scripts/gh-wire-pages-api.sh https://your-api.example.com/api/v1
#   ./scripts/gh-wire-pages-api.sh https://your-api.example.com/api/v1 your-x-api-key
#
# Environment:
#   REPO  GitHub repo (default: Chessing234/ANVIL)

set -euo pipefail
REPO="${REPO:-Chessing234/ANVIL}"

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <TUTORIAL_PAGES_API_URL> [TUTORIAL_PAGES_API_KEY]" >&2
  exit 1
fi

API_URL="$1"
if [[ "$API_URL" != https://* ]]; then
  echo "error: API URL must start with https:// (GitHub Pages is HTTPS-only)." >&2
  exit 1
fi

gh variable set TUTORIAL_PAGES_API_URL -b "$API_URL" -R "$REPO"

if [[ $# -ge 2 ]]; then
  printf '%s' "$2" | gh secret set TUTORIAL_PAGES_API_KEY -R "$REPO"
else
  echo "note: no API key passed; set TUTORIAL_PAGES_API_KEY later with:" >&2
  echo "  printf '%s' 'your-key' | gh secret set TUTORIAL_PAGES_API_KEY -R $REPO" >&2
fi

gh workflow run "Tutorial — GitHub Pages" -R "$REPO"
echo "Triggered \"Tutorial — GitHub Pages\". Watch: gh run list -R $REPO --workflow \"Tutorial — GitHub Pages\" --limit 3"
