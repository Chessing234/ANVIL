"""Tests for sandbox generation, sanitization, and mock container isolation."""

from __future__ import annotations

from uuid import uuid4

import pytest

from agents.teaching.narrative_generation import NarrativeGenerationAgent
from agents.teaching.sandbox_generation import SandboxGenerationAgent
from agents.teaching.education_models import SandboxStatus
from agents.teaching.tools.sandbox_builder import SandboxBuilder
from agents.teaching.tools.sandbox_sanitizers import run_full_pipeline, SanitizationAudit
from config.constants import IncidentSeverity
from core.message_bus import MessageBus
from shared.models import Incident, InvestigationStep, StudentProfile


@pytest.mark.asyncio
async def test_sanitization_rewrites_documentation_ip(tmp_path) -> None:
    audit = SanitizationAudit()
    raw = "Contact 198.51.100.44 and user@secret.example.com"
    out, _ = run_full_pipeline(raw, audit)
    assert "192.0.2." in out
    assert "[REDACTED_EMAIL]" in out
    assert audit.entries


@pytest.mark.asyncio
async def test_sandbox_builder_snapshot_roundtrip(tmp_path) -> None:
    cfg = {"sandbox_workspace_root": str(tmp_path / "sb")}
    b = SandboxBuilder(cfg)
    info = await b.create_container()
    from agents.teaching.education_models import SandboxArtifact, NetworkConfig

    arts = [
        SandboxArtifact(
            id="a1",
            virtual_path="/evidence/log.txt",
            description="sample",
        ),
    ]
    await b.copy_artifacts(info.container_id, arts)
    await b.setup_network(info.container_id, NetworkConfig(internal_only=True))
    await b.install_tools(info.container_id, ["grep", "strings"])
    snap = await b.capture_state(info.container_id)
    work = tmp_path / "sb" / info.container_id / "work"
    (work / "mutate.txt").write_text("changed", encoding="utf-8")
    await b.reset_to_state(info.container_id, snap)
    assert not (work / "mutate.txt").exists()
    assert await b.health_check(info.container_id)
    await b.destroy(info.container_id)
    assert not (tmp_path / "sb" / info.container_id).exists()


@pytest.mark.asyncio
async def test_generate_sandbox_pipeline(tmp_path) -> None:
    bus = MessageBus()
    iid = uuid4()
    inc = Incident(
        id=iid,
        title="Lab incident",
        description="training scenario",
        severity=IncidentSeverity.MEDIUM,
    )
    steps = [
        InvestigationStep(
            incident_id=iid,
            agent_name="defense",
            action_taken="log_review",
            tool_used="grep",
            interpretation="suspicious login from 198.51.100.10",
            raw_output="198.51.100.10",
            confidence=0.8,
        ),
    ]
    narrative_agent = NarrativeGenerationAgent(bus, {})
    narrative = await narrative_agent.generate_narrative(
        steps,
        inc,
        StudentProfile(name="Alex", experience_level="intermediate"),
    )
    cfg = {"sandbox_workspace_root": str(tmp_path / "sand")}
    sandbox_agent = SandboxGenerationAgent(bus, cfg)
    sandbox = await sandbox_agent.generate_sandbox(steps, narrative)
    assert sandbox.status == SandboxStatus.READY
    assert sandbox.sanitized
    assert sandbox.container_id
    assert sandbox.challenges
    assert "no outbound" in sandbox.isolation_notes.lower() or "internet" in sandbox.isolation_notes.lower()
    for art in sandbox.artifacts:
        assert "198.51.100" not in art.description
        assert "192.0.2." in art.description or "[REDACTED" in art.description or "empty" in art.description.lower()

    await SandboxBuilder(cfg).destroy(sandbox.container_id)
