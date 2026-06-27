"""Lightweight LLM completion helper for orchestration workflows."""

from __future__ import annotations

import httpx
import structlog

from config.settings import Settings, get_settings

logger = structlog.get_logger(__name__)


async def complete_text(
    prompt: str,
    *,
    system_prompt: str | None = None,
    settings: Settings | None = None,
    temperature: float | None = None,
    max_tokens: int = 512,
) -> str | None:
    """Return model text when ``TUTORIAL_LLM__API_KEY`` is configured; otherwise ``None``."""

    cfg = settings or get_settings()
    api_key = (cfg.llm.api_key or "").strip()
    if not api_key:
        return None

    model = cfg.llm.model_name
    base = str(cfg.llm.base_url).rstrip("/")
    temp = cfg.llm.temperature_creative if temperature is None else temperature
    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": model,
        "temperature": temp,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    timeout = httpx.Timeout(float(cfg.llm.timeout_seconds))

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(f"{base}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return str(data["choices"][0]["message"]["content"]).strip()
    except Exception as exc:
        logger.warning("llm_complete_failed", error=str(exc))
        return None
