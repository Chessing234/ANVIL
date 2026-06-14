"""MCP server exposing LLM-style primitives with pluggable backends and rate limits."""

from __future__ import annotations

import asyncio
import math
import os
import re
import time
from collections import deque
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("tutorial-llm-server", warn_on_duplicate_tools=False)

_RATE_WINDOW_SECONDS = 60.0
_MAX_REQUESTS_PER_WINDOW = int(os.environ.get("LLM_MCP_MAX_RPM", "60"))
_last_calls: deque[float] = deque()
_rate_lock = asyncio.Lock()


async def _throttle() -> None:
    async with _rate_lock:
        now = time.monotonic()
        while _last_calls and now - _last_calls[0] > _RATE_WINDOW_SECONDS:
            _last_calls.popleft()
        if len(_last_calls) >= _MAX_REQUESTS_PER_WINDOW:
            wait = _RATE_WINDOW_SECONDS - (now - _last_calls[0])
            await asyncio.sleep(max(wait, 0.05))
            now = time.monotonic()
            while _last_calls and now - _last_calls[0] > _RATE_WINDOW_SECONDS:
                _last_calls.popleft()
        _last_calls.append(time.monotonic())


def _estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


async def _openai_complete(prompt: str, system_prompt: str | None, temperature: float, max_tokens: int) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    if not api_key:
        raise RuntimeError("missing OPENAI_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": (
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}]
            if system_prompt
            else [{"role": "user", "content": prompt}]
        ),
    }
    timeout = httpx.Timeout(60.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{base.rstrip('/')}/chat/completions", headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        return str(data["choices"][0]["message"]["content"])


@mcp.tool()
async def complete(
    prompt: str,
    system_prompt: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 512,
) -> dict[str, Any]:
    """Text completion with OpenAI-compatible backends or deterministic stubs."""

    await _throttle()
    tokens = _estimate_tokens(prompt) + _estimate_tokens(system_prompt or "")
    try:
        text = await _openai_complete(prompt, system_prompt, temperature, max_tokens)
        return {"ok": True, "text": text, "tokens_estimated": tokens, "backend": "openai"}
    except BaseException:
        summary = f"[llm-stub]{prompt[:400]}"
        return {"ok": True, "text": summary, "tokens_estimated": tokens, "backend": "stub"}


@mcp.tool()
async def embed(texts: list[str]) -> dict[str, Any]:
    """Return lightweight pseudo-embeddings (hash-based) for offline tests."""

    await _throttle()
    vectors: list[list[float]] = []
    for line in texts:
        seed = abs(hash(line)) % (2**32)
        rng = random_from_seed(seed)
        vectors.append([round(rng(), 6) for _ in range(8)])
    return {"ok": True, "vectors": vectors, "dimensions": 8}


def random_from_seed(seed: int) -> Any:
    """Deterministic PRNG closure."""

    state = seed

    def _next() -> float:
        nonlocal state
        state = (1103515245 * state + 12345) % (2**31)
        return (state % 10_000) / 10_000.0

    return _next


@mcp.tool()
async def classify(text: str, labels: list[str]) -> dict[str, Any]:
    """Zero-shot style classification using keyword overlap."""

    await _throttle()
    scores = {label: sum(1 for w in label.lower().split("_") if w and w in text.lower()) for label in labels}
    best = max(labels, key=lambda lbl: scores.get(lbl, 0)) if labels else "unknown"
    return {"ok": True, "label": best, "scores": scores}


@mcp.tool()
async def summarize(text: str, max_sentences: int = 3) -> dict[str, Any]:
    """Extractive summarization without external calls."""

    await _throttle()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    summary = " ".join(sentences[: max(1, max_sentences)])
    return {"ok": True, "summary": summary or text[:400]}


@mcp.tool()
async def extract_entities(text: str) -> dict[str, Any]:
    """Simple capitalized-token entity heuristic."""

    await _throttle()
    tokens = re.findall(r"\b(?:[A-Z][a-z]+){2,}\b", text)
    return {"ok": True, "entities": sorted(set(tokens))}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
