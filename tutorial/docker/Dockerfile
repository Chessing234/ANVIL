# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/home/tutorial/.local/bin:${PATH}"

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash tutorial

WORKDIR /app

COPY pyproject.toml README.md ./
COPY config ./config
COPY core ./core
COPY shared ./shared

RUN pip install --upgrade pip && pip install --user .

USER tutorial

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import config; import core; import shared; print('ok')"

CMD ["python", "-c", "import asyncio; asyncio.run(__import__('asyncio').sleep(10**9))"]
