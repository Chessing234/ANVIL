"""GitLab CI/CD security scanning helpers and educational issue creation."""

from __future__ import annotations

import json
import textwrap
from typing import Any

import structlog
from pydantic import BaseModel, Field

from platforms.gitlab.orbit_connector import GitLabOrbitConnector

logger = structlog.get_logger(__name__)


class SecurityFinding(BaseModel):
    """Normalized security finding from SAST, dependency, or secret scans."""

    model_config = {"extra": "forbid"}

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    severity: str = Field(min_length=1)
    category: str = Field(min_length=1)
    description: str = Field(default="")
    file_path: str | None = None
    line: int | None = None
    tool: str = Field(min_length=1, description="sast | dependency | secret")


def _artifact_paths_for_job(name: str) -> list[str]:
    lowered = name.lower()
    if "sast" in lowered:
        return ["gl-sast-report.json"]
    if "dependency" in lowered or "gemnasium" in lowered:
        return ["gl-dependency-scanning-report.json"]
    if "secret" in lowered or "truffle" in lowered:
        return ["gl-secret-detection-report.json"]
    return []


def _parse_sast_like(data: dict[str, Any], tool: str) -> list[SecurityFinding]:
    out: list[SecurityFinding] = []
    vulns = data.get("vulnerabilities")
    if not isinstance(vulns, list):
        return out
    for item in vulns:
        if not isinstance(item, dict):
            continue
        fid = str(item.get("id") or item.get("uuid") or item.get("name") or "finding")
        name = str(item.get("name") or item.get("message") or "Security finding")
        sev = str(item.get("severity") or "Unknown")
        desc = str(item.get("description") or item.get("details") or "")
        category = str(item.get("category") or "SAST")
        loc = item.get("location") if isinstance(item.get("location"), dict) else {}
        file_path = None
        line_no = None
        if isinstance(loc, dict):
            file_path = loc.get("file") or loc.get("path")
            line_no = loc.get("start_line") or loc.get("line")
        cwe = None
        for ident in item.get("identifiers") or []:
            if isinstance(ident, dict) and ident.get("type") == "cwe":
                cwe = ident.get("name")
                break
        if cwe:
            category = f"{category} ({cwe})"
        out.append(
            SecurityFinding(
                id=fid,
                name=name,
                severity=sev,
                category=category,
                description=desc,
                file_path=str(file_path) if file_path else None,
                line=int(line_no) if isinstance(line_no, int) else None,
                tool=tool,
            )
        )
    return out


def _parse_dependency_report(data: dict[str, Any]) -> list[SecurityFinding]:
    vulns = data.get("vulnerabilities")
    if isinstance(vulns, list) and vulns:
        return _parse_sast_like(data, "dependency")
    files = data.get("dependency_files") or []
    out: list[SecurityFinding] = []
    if isinstance(files, list):
        for dep_file in files:
            if not isinstance(dep_file, dict):
                continue
            for v in dep_file.get("vulnerabilities") or []:
                if not isinstance(v, dict):
                    continue
                out.append(
                    SecurityFinding(
                        id=str(v.get("id") or v.get("name") or f"dep-{len(out)}"),
                        name=str(v.get("name") or "Dependency vulnerability"),
                        severity=str(v.get("severity") or "Unknown"),
                        category="Dependency",
                        description=str(v.get("description") or ""),
                        file_path=str(dep_file.get("path") or ""),
                        line=None,
                        tool="dependency",
                    )
                )
    return out


class CISecurityScanner:
    """Generates non-blocking GitLab CI security jobs and turns reports into teaching issues."""

    def __init__(self, connector: GitLabOrbitConnector) -> None:
        self._connector = connector

    async def generate_ci_config(self, project_type: str) -> str:
        """Return a ``.gitlab-ci.yml`` fragment with **allow_failure** security jobs (non-blocking)."""
        image = "python:3.12-slim"
        if project_type.lower() in {"node", "javascript", "typescript"}:
            image = "node:22-bookworm-slim"
        elif project_type.lower() in {"go", "golang"}:
            image = "golang:1.22-bookworm"
        elif project_type.lower() in {"java", "kotlin", "gradle", "maven"}:
            image = "eclipse-temurin:21-jdk"

        return textwrap.dedent(
            f"""
            stages:
              - test
              - security

            default:
              image: {image}

            variables:
              SECURE_LOG_LEVEL: "info"

            # SAST (Static Application Security Testing) — non-blocking
            sast:
              stage: security
              allow_failure: true
              script:
                - docker run --rm -v "$PWD:/app" -w /app securecodewarrior/sast-scan:latest
              artifacts:
                when: always
                reports:
                  sast: gl-sast-report.json

            # Dependency Scanning — non-blocking
            dependency_scanning:
              stage: security
              allow_failure: true
              script:
                - docker run --rm -v "$PWD:/app" -w /app registry.gitlab.com/security-products/gemnasium-maven:latest
              artifacts:
                when: always
                reports:
                  dependency_scanning: gl-dependency-scanning-report.json

            # Secret Detection — non-blocking
            secret_detection:
              stage: security
              allow_failure: true
              script:
                - docker run --rm -v "$PWD:/app" -w /app trufflesecurity/trufflehog:latest git file://.
              artifacts:
                when: always
                reports:
                  secret_detection: gl-secret-detection-report.json
            """
        ).strip()

    async def parse_scan_results(self, project_id: str, pipeline_id: str) -> list[SecurityFinding]:
        """Download standard GitLab security report artifacts for jobs in a pipeline."""
        jobs = await self._connector.list_pipeline_jobs(project_id, pipeline_id)
        aggregated: list[SecurityFinding] = []
        for job in jobs:
            job_id = int(job.get("id") or 0)
            name = str(job.get("name") or "")
            if not job_id:
                continue
            for artifact_path in _artifact_paths_for_job(name):
                try:
                    raw = await self._connector.download_job_artifact(
                        project_id, job_id, artifact_path
                    )
                except RuntimeError as exc:
                    logger.warning("artifact_download_failed", job=job_id, path=artifact_path, err=str(exc))
                    continue
                try:
                    data = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    logger.warning("artifact_parse_failed", job=job_id, path=artifact_path, err=str(exc))
                    continue
                if not isinstance(data, dict):
                    continue
                if "sast" in artifact_path:
                    aggregated.extend(_parse_sast_like(data, "sast"))
                elif "dependency" in artifact_path:
                    aggregated.extend(_parse_dependency_report(data))
                elif "secret" in artifact_path:
                    aggregated.extend(_parse_sast_like(data, "secret"))
        return aggregated

    async def create_security_issues(
        self,
        project_id: str,
        findings: list[SecurityFinding],
    ) -> list[int]:
        """Create one GitLab issue per finding with educational context."""
        created: list[int] = []
        for finding in findings:
            body = await self.generate_educational_feedback(finding)
            issue = await self._connector.create_issue(
                project_id,
                title=f"[{finding.tool.upper()}] {finding.name}",
                description=body,
                labels=["security", "tutorial-ci", finding.tool],
            )
            created.append(issue.iid)
        return created

    async def generate_educational_feedback(self, finding: SecurityFinding) -> str:
        """Produce Markdown explaining the risk and remediation for learners."""
        loc = ""
        if finding.file_path:
            loc = f"`{finding.file_path}`"
            if finding.line is not None:
                loc += f":{finding.line}"
        return textwrap.dedent(
            f"""
            ## TUTORIAL — CI security coaching

            **Tool**: {finding.tool}
            **Severity**: {finding.severity}
            **Category**: {finding.category}

            ### What happened
            {finding.description or finding.name}

            ### Why it matters
            CI findings highlight classes of defects that become breaches when they reach production.
            Treat each finding as a chance to practice **secure defaults**, **least privilege**, and
            **defense in depth**.

            ### What to do next
            1. Reproduce locally using the same scanner image as CI.
            2. Patch the vulnerable dependency or remove the dangerous pattern.
            3. Add a regression test or policy-as-code rule so the issue cannot return silently.

            **Location**: {loc or "_(see pipeline job logs)_"}

            _This issue is informational when `allow_failure: true` is set — fix before release._
            """
        ).strip()
