"""Docker artifacts for multi-arch edge deployments (local-first TUTORIAL agents)."""

from __future__ import annotations

import textwrap


def edge_dockerfile(*, base_image: str = "python:3.12-alpine3.20") -> str:
    """Return a minimal multi-stage friendly Dockerfile string for edge nodes."""
    return textwrap.dedent(
        f"""
        # syntax=docker/dockerfile:1.6
        FROM --platform=$BUILDPLATFORM {base_image} AS base
        WORKDIR /app
        ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

        RUN apk add --no-cache sqlite-libs ca-certificates wget

        COPY . /app
        RUN pip install --upgrade pip && pip install .

        EXPOSE 8787
        HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \\
          CMD wget -qO- http://127.0.0.1:8787/ || exit 1

        CMD ["python", "-m", "http.server", "8787", "--bind", "0.0.0.0", "--directory", "/app"]
        """
    ).strip()


def edge_compose_fragment(service_name: str = "tutorial-edge") -> str:
    """Return a docker-compose service fragment with resource limits and restart policy."""
    return textwrap.dedent(
        f"""
        services:
          {service_name}:
            build:
              context: .
              dockerfile: Dockerfile.edge
            image: tutorial-edge:latest
            restart: unless-stopped
            deploy:
              resources:
                limits:
                  cpus: "2.0"
                  memory: 2G
                reservations:
                  cpus: "0.25"
                  memory: 256M
            environment:
              EDGE_LOCAL_FIRST: "1"
            healthcheck:
              test: ["CMD", "wget", "-qO-", "http://127.0.0.1:8787/"]
              interval: 30s
              timeout: 5s
              retries: 3
        """
    ).strip()


def buildx_bake_edge_targets() -> str:
    """Return a minimal ``docker buildx bake`` HCL snippet for ARM64 + AMD64."""
    return textwrap.dedent(
        """
        target "edge-default" {
          context = "."
          dockerfile = "Dockerfile.edge"
          platforms = ["linux/amd64", "linux/arm64"]
          tags = ["tutorial-edge:local"]
        }
        """
    ).strip()
