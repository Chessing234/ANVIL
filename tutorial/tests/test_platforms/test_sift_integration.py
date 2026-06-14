"""Integration tests for SIFT connector, playbooks, self-correction, and reports."""

from __future__ import annotations

from pathlib import Path

import pytest

from platforms.sift.accuracy_report import AccuracyReportGenerator
from platforms.sift.connector import SIFTConnector
from platforms.sift.execution_engine import SIFTExecutionEngine
from platforms.sift.playbook_runner import PlaybookRunner
from platforms.sift.self_correction import SelfCorrectingInvestigator, evaluate_result_quality
from shared.models import Incident, IncidentSeverity


@pytest.fixture
def mock_connector() -> SIFTConnector:
    return SIFTConnector(mock=True, max_reconnect_attempts=2)


@pytest.fixture
def sample_incident() -> Incident:
    return Incident(
        title="FIND EVIL! lab scenario",
        description="Synthetic incident for SIFT integration tests.",
        severity=IncidentSeverity.HIGH,
    )


@pytest.mark.asyncio
async def test_connector_connect_execute(mock_connector: SIFTConnector) -> None:
    await mock_connector.connect(host="127.0.0.1", port=22)
    res = await mock_connector.execute_command("echo hello", timeout=10.0)
    assert "hello" in res.stdout
    assert res.exit_code == 0
    await mock_connector.disconnect()


@pytest.mark.asyncio
async def test_playbook_runner_triage(mock_connector: SIFTConnector, tmp_path: Path) -> None:
    ev = tmp_path / "sample.mem"
    ev.write_bytes(b"\x00" * 1024)
    runner = PlaybookRunner(mock_connector)
    pb = await PlaybookRunner.load_playbook("triage.yml")
    ctx = {"evidence_path": str(ev), "working_dir": "/cases/test", "previous": {}}
    result = await runner.run_playbook(pb, ctx)
    assert result.progress_percent == 100.0
    assert not result.aborted
    names = [s.name for s in result.steps]
    assert "List_Processes" in names


@pytest.mark.asyncio
async def test_self_correction_triggers(mock_connector: SIFTConnector, tmp_path: Path) -> None:
    ev = tmp_path / "memdump.mem"
    ev.write_bytes(b"\x00" * 2048)
    incident = Incident(
        title="Self-correction scenario",
        description="Exercise low-quality first pass.",
        severity=IncidentSeverity.MEDIUM,
    )
    inv = SelfCorrectingInvestigator(incident, mock_connector, default_playbook="triage.yml")
    out = await inv.investigate([str(ev)])
    assert len(out.steps) >= 1
    events = out.accuracy_report.get("find_evil_correction_events", [])
    assert isinstance(events, list)
    assert len(events) >= 1


@pytest.mark.asyncio
async def test_accuracy_report_generation(
    mock_connector: SIFTConnector,
    tmp_path: Path,
    sample_incident: Incident,
) -> None:
    ev = tmp_path / "disk.raw"
    ev.write_bytes(b"\x00" * 512)
    inv = SelfCorrectingInvestigator(sample_incident, mock_connector, default_playbook="triage.yml")
    result = await inv.investigate([str(ev)])
    gen = AccuracyReportGenerator()
    report = gen.generate_report(result)
    assert report.self_corrections_performed > 0
    assert report.accuracy_score > 0.0
    json_path = tmp_path / "report.json"
    md_path = tmp_path / "report.md"
    gen.write_json(report, str(json_path))
    gen.write_markdown(report, str(md_path))
    assert json_path.is_file()
    assert "FIND EVIL!" in md_path.read_text(encoding="utf-8")


def test_evaluate_result_quality_empty_json() -> None:
    q = evaluate_result_quality(
        "t",
        {"stdout": "{}", "stderr": "", "exit_code": 0, "parsed": {}},
    )
    assert q.value < 0.5


@pytest.mark.asyncio
async def test_execution_engine_run_investigation(
    mock_connector: SIFTConnector,
    tmp_path: Path,
    sample_incident: Incident,
) -> None:
    img = tmp_path / "evidence.raw"
    img.write_bytes(b"\x00" * 4096)
    eng = SIFTExecutionEngine(mock_connector)
    sift_result = await eng.run_investigation([str(img)], sample_incident)
    assert sift_result.investigation_id
    assert sift_result.working_dir
    assert isinstance(sift_result.execution_log, list)
