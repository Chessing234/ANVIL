#!/usr/bin/env python3
"""Write FastAPI OpenAPI JSON to docs/openapi.json for documentation and CI artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.main import create_app  # noqa: E402


def main() -> None:
    out = ROOT / "docs" / "openapi.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    spec = create_app().openapi()
    out.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
