#!/usr/bin/env python3
"""Run the FastAPI development server with auto-reload."""

from __future__ import annotations

import sys

import uvicorn


def main() -> None:
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        loop="asyncio",
    )


if __name__ == "__main__":
    sys.exit(main() or 0)
