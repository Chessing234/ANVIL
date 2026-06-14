"""Tests for GitLab Orbit, secure MR education, CI security, and Orbit skills."""

from __future__ import annotations

import json

import pytest

from platforms.gitlab import (
    TRANSCEND_SHOWCASE_SUBMISSION,
    CISecurityScanner,
    GitLabOrbitConnector,
    SecurityFinding,
)
from platforms.gitlab.agent_skills import (
    CODE_REVIEW_SKILL,
    SECURE_PRACTICE_SKILL,
    VULNERABILITY_SCAN_SKILL,
)
from platforms.gitlab.orbit_connector import FlowStep
from platforms.gitlab.secure_code_edu import SecureCodingEducator


@pytest.fixture
async def connector() -> GitLabOrbitConnector:
    conn = GitLabOrbitConnector("https://gitlab.example", mock=True)
    yield conn
    await conn.close()


@pytest.mark.asyncio
async def test_orbit_connector_agent_flow_skill(connector: GitLabOrbitConnector) -> None:
    agent = await connector.create_agent("sec-tutor", "Explains OWASP", ["code_review"])
    assert agent.name == "sec-tutor"
    assert agent.skills == ["code_review"]

    flow = await connector.create_flow(
        "mr-security",
        [FlowStep(name="fetch", action="gitlab.fetch_mr", parameters={"ref": "main"})],
    )
    assert flow.steps[0].action == "gitlab.fetch_mr"

    skill = await connector.create_skill(
        "lint-secrets",
        "Detect secrets in diffs",
        ["secret_detector"],
    )
    assert "secret" in skill.prompt.lower()

    result = await connector.trigger_flow(flow.id, {"mr": 12})
    assert result.status == "completed"
    assert result.outputs["mr"] == 12


@pytest.mark.asyncio
async def test_orbit_connector_review_issue_comment(connector: GitLabOrbitConnector) -> None:
    review = await connector.get_code_review("group/project", 5)
    assert "group/project!5" == review.mr_id

    issue = await connector.create_issue(
        "group/project",
        "Leak",
        "Rotate token",
        ["security"],
    )
    assert issue.iid >= 1

    await connector.comment_on_mr("group/project", 5, "Nice work")
    assert connector._mock_comments[-1][2].startswith("Nice")  # noqa: SLF001


@pytest.mark.asyncio
async def test_secure_coding_educator_detects_sqli(connector: GitLabOrbitConnector) -> None:
    educator = SecureCodingEducator(connector, lesson_base_url="https://kb.example")
    review = await educator.review_and_teach("group/project", 9)
    assert review.overall_risk == "HIGH"
    assert review.issues_found
    assert any("Injection" in issue.category for issue in review.issues_found)
    assert review.educational_content
    assert connector._mock_comments  # noqa: SLF001


@pytest.mark.asyncio
async def test_secure_coding_educator_clean_diff() -> None:
    class CleanConnector(GitLabOrbitConnector):
        async def get_merge_request_changes(  # type: ignore[override]
            self, project_id: str, merge_request_iid: int
        ) -> list[dict]:
            return [{"new_path": "app.py", "diff": "+SAFE_CONSTANT = 42\n"}]

    conn = CleanConnector("https://gitlab.example", mock=True)
    try:
        edu = SecureCodingEducator(conn)
        review = await edu.review_and_teach("g/p", 1)
        assert review.overall_risk == "LOW"
        assert review.issues_found == []
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_ci_security_scanner_yaml_and_parse(connector: GitLabOrbitConnector) -> None:
    scanner = CISecurityScanner(connector)
    yml = await scanner.generate_ci_config("python")
    assert "allow_failure: true" in yml
    assert "gl-sast-report.json" in yml
    assert "dependency_scanning:" in yml

    findings = await scanner.parse_scan_results("g/p", "123")
    assert isinstance(findings, list)
    severities = {f.severity for f in findings}
    assert severities

    feedback = await scanner.generate_educational_feedback(
        SecurityFinding(
            id="f1",
            name="Test",
            severity="High",
            category="SAST",
            description="Demo",
            file_path="x.py",
            line=10,
            tool="sast",
        )
    )
    assert "TUTORIAL" in feedback

    iids = await scanner.create_security_issues(
        "g/p",
        [
            SecurityFinding(
                id="f2",
                name="Another",
                severity="Medium",
                category="Dependency",
                tool="dependency",
            )
        ],
    )
    assert iids == [1]


def test_ci_security_parses_inline_report_bytes() -> None:
    raw = {
        "vulnerabilities": [
            {
                "id": "inline-1",
                "name": "Hardcoded password",
                "severity": "Critical",
                "description": "Password in source",
                "location": {"file": "config.py", "start_line": 4},
                "identifiers": [{"type": "cwe", "name": "CWE-798"}],
            }
        ]
    }
    findings = _parse_sast_like_helper(raw, "sast")
    assert findings[0].tool == "sast"
    assert findings[0].file_path == "config.py"


def _parse_sast_like_helper(data: dict, tool: str) -> list:
    from platforms.gitlab.ci_security import _parse_sast_like

    return _parse_sast_like(data, tool)


def test_orbit_skills_are_well_formed() -> None:
    for skill in (CODE_REVIEW_SKILL, VULNERABILITY_SCAN_SKILL, SECURE_PRACTICE_SKILL):
        assert skill.system_prompt
        assert skill.tools
        assert skill.input_description and len(skill.input_description) > 8
        assert skill.output_description


def test_showcase_submission_markdown() -> None:
    assert "Transcend" in TRANSCEND_SHOWCASE_SUBMISSION
    assert "GitLab Orbit" in TRANSCEND_SHOWCASE_SUBMISSION


def test_gitlab_package_exports() -> None:
    import platforms.gitlab as gl

    assert hasattr(gl, "GitLabOrbitConnector")
    assert hasattr(gl, "SecureCodingEducator")
    assert hasattr(gl, "CISecurityScanner")


@pytest.mark.asyncio
async def test_merge_request_changes_mock_shape(connector: GitLabOrbitConnector) -> None:
    changes = await connector.get_merge_request_changes("g/p", 3)
    assert changes[0]["new_path"] == "app.py"
    assert "SELECT" in changes[0]["diff"]


@pytest.mark.asyncio
async def test_download_job_artifact_mock_variants(connector: GitLabOrbitConnector) -> None:
    sast = await connector.download_job_artifact("g/p", 9001, "gl-sast-report.json")
    assert json.loads(sast.decode())["vulnerabilities"]

    dep = await connector.download_job_artifact("g/p", 9002, "gl-dependency-scanning-report.json")
    body = json.loads(dep.decode())
    assert "vulnerabilities" in body

    sec = await connector.download_job_artifact("g/p", 9003, "gl-secret-detection-report.json")
    assert json.loads(sec.decode())["vulnerabilities"]
