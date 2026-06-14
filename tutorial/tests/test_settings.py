"""Tests for configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from config.settings import Settings, get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> None:
    """Ensure ``get_settings`` reads fresh environment values."""

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Environment variables populate nested settings."""

    monkeypatch.setenv("TUTORIAL_LLM__MODEL_NAME", "custom-model")
    monkeypatch.setenv("TUTORIAL_AGENTS__MAX_CONCURRENT_AGENTS", "4")
    monkeypatch.setenv("TUTORIAL_DATABASE__URL", "sqlite:///./tmp.db")
    settings = Settings()
    assert settings.llm.model_name == "custom-model"
    assert settings.agents.max_concurrent_agents == 4
    assert settings.database.url.startswith("sqlite:")


def test_invalid_database_url_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unsupported schemes are rejected."""

    monkeypatch.setenv("TUTORIAL_DATABASE__URL", "mysql://bad")
    with pytest.raises(ValueError):
        Settings()


def test_get_agent_config_merges_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    """Per-agent overrides merge into shared defaults."""

    overrides = '{"tutor":{"llm":{"temperature_agents":0.4}}}'
    monkeypatch.setenv("TUTORIAL_AGENTS__PER_AGENT_OVERRIDES_JSON", overrides)
    settings = Settings()
    cfg = settings.get_agent_config("tutor")
    assert cfg["llm"]["temperature_agents"] == 0.4
    assert cfg["llm"]["model_name"] == settings.llm.model_name


def test_optional_paths_validated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Filesystem paths must exist when provided."""

    missing = tmp_path / "nowhere"
    monkeypatch.setenv("TUTORIAL_SECURITY__SIFT_WORKSTATION_PATH", str(missing))
    with pytest.raises(ValueError):
        Settings()
