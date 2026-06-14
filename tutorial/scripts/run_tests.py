#!/usr/bin/env python3
"""Run pytest with coverage defaults for TUTORIAL."""

from __future__ import annotations

import subprocess
import sys


def main() -> int:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        "-v",
        "--tb=short",
        "--cov=tutorial",
        "--cov=api",
        "--cov=database",
        "--cov=orchestration",
        "--cov=config",
        "--cov=core",
        "--cov=integrations",
        "--cov=agents",
        "--cov=knowledge",
        "--cov=platforms",
        "--cov=events",
        "--cov=shared",
        "--cov-report=term-missing",
    ]
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
