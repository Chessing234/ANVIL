"""Secure coding education tied to GitLab merge requests and TUTORIAL knowledge base."""

from __future__ import annotations

import os
import re
from typing import Iterator

import structlog
from pydantic import BaseModel, Field

from platforms.gitlab.orbit_connector import GitLabOrbitConnector

logger = structlog.get_logger(__name__)


class SecurityIssue(BaseModel):
    """Single security finding with OWASP-oriented metadata."""

    model_config = {"extra": "forbid"}

    file: str = Field(min_length=1)
    line: int = Field(ge=0)
    severity: str = Field(min_length=1)
    category: str = Field(min_length=1)
    description: str = Field(min_length=1)
    fix_suggestion: str = Field(min_length=1)
    educational_explanation: str = Field(min_length=1)
    related_lesson_id: str | None = None
    cwe_id: str | None = None


class LessonSnippet(BaseModel):
    """Short educational artifact derived from a finding."""

    model_config = {"extra": "forbid"}

    title: str = Field(min_length=1)
    body_markdown: str = Field(min_length=1)
    related_lesson_url: str | None = None


class SecurityReview(BaseModel):
    """Aggregate MR security review with teaching hooks."""

    model_config = {"extra": "forbid"}

    mr_id: str = Field(min_length=1)
    issues_found: list[SecurityIssue] = Field(default_factory=list)
    educational_content: list[LessonSnippet] = Field(default_factory=list)
    overall_risk: str = Field(min_length=1)
    learning_opportunities: list[str] = Field(default_factory=list)


# Transcend hackathon — narrative for the Showcase Track (TUTORIAL × GitLab Orbit).
TRANSCEND_SHOWCASE_SUBMISSION = """# TUTORIAL × GitLab Orbit — Transcend Showcase

## Summary
Project TUTORIAL integrates with **GitLab Orbit** patterns (agents, flows, skills) and **GitLab API v4**
to deliver **secure development education** at the point of code review and CI. We combine:

- **Orbit-style automation** (`GitLabOrbitConnector`) for agents, flows, and reusable skills.
- **Merge-request teaching** (`SecureCodingEducator`) that maps findings to **OWASP** categories,
  **CWE** references, fix patterns, and **TUTORIAL lesson** deep links.
- **Non-blocking CI security** (`CISecurityScanner`) so pipelines stay green while learners receive
  SAST, dependency, and secret-detection feedback as GitLab issues and MR comments.

## Why it matters
Security education fails when it is generic. This integration grounds lessons in **real diffs** and
**real pipeline findings**, turning every MR into a micro-curriculum without blocking delivery.

## Demo checklist
1. Open a merge request with an intentional (safe) vulnerable pattern in a feature branch.
2. Run `SecureCodingEducator.review_and_teach` — MR receives a structured, educational comment.
3. Add generated `.gitlab-ci.yml` security jobs — review parsed `SecurityFinding` objects as issues.

Built for the **GitLab Transcend** hackathon secure-development education track.
"""


_RULE = tuple[str, str, str, str, re.Pattern[str], str, str, str]
# name, severity, OWASP category, CWE, pattern, fix hint, education, lesson slug

_SECURITY_RULES: list[_RULE] = [
    (
        "SQL Injection",
        "HIGH",
        "A03:2021 – Injection",
        "CWE-89",
        re.compile(
            r"(execute\s*\(\s*f[\"']|execute\s*\(\s*[\"'][^\"']*%s|raw\s*\(|"
            r"cursor\.execute\s*\(\s*f[\"'])",
            re.IGNORECASE,
        ),
        "Use parameterized queries / bound parameters; never interpolate user input into SQL text.",
        "Concatenating user-controlled values into SQL lets attackers alter query logic. "
        "Parameterized APIs separate code from data so inputs cannot become syntax.",
        "injection-sql",
    ),
    (
        "Cross-site Scripting (XSS)",
        "MEDIUM",
        "A03:2021 – Injection",
        "CWE-79",
        re.compile(
            r"(innerHTML\s*=|dangerouslySetInnerHTML|document\.write\s*\()",
            re.IGNORECASE,
        ),
        "Prefer textContent, React escaping, CSP, and sanitization libraries with strict allowlists.",
        "Browser APIs that write raw HTML execute attacker-controlled markup as code in the user's session.",
        "injection-xss",
    ),
    (
        "Cross-Site Request Forgery (CSRF) risk",
        "MEDIUM",
        "A01:2021 – Broken Access Control",
        "CWE-352",
        re.compile(r"(@csrf_exempt|csrf_exempt\s*\(|SameSite\s*=\s*[\"']None[\"'])", re.IGNORECASE),
        "Keep CSRF protections enabled; use SameSite=Lax/Strict cookies and double-submit tokens for stateful actions.",
        "Disabling CSRF protections lets attackers trick browsers into performing authenticated actions.",
        "broken-access-csrf",
    ),
    (
        "Insecure Deserialization",
        "HIGH",
        "A08:2021 – Software and Data Integrity Failures",
        "CWE-502",
        re.compile(r"(pickle\.loads|yaml\.unsafe_load|marshal\.loads)\s*\(", re.IGNORECASE),
        "Never deserialize untrusted blobs with pickle/marshal; use yaml.safe_load and signed formats.",
        "Attackers can craft payloads that execute code during deserialization.",
        "integrity-deserialization",
    ),
    (
        "Broken Authentication",
        "HIGH",
        "A07:2021 – Identification and Authentication Failures",
        "CWE-798",
        re.compile(
            r"(password\s*=\s*[\"'][^\"']+[\"']|api_key\s*=\s*[\"'][^\"']+[\"']|"
            r"AWS_SECRET_ACCESS_KEY\s*=)",
            re.IGNORECASE,
        ),
        "Load secrets from environment or a secret manager; rotate credentials if exposed.",
        "Hard-coded credentials leak through source control and supply-chain mirrors.",
        "broken-auth-secrets",
    ),
    (
        "Sensitive Data Exposure",
        "MEDIUM",
        "A02:2021 – Cryptographic Failures",
        "CWE-359",
        re.compile(r"(print\s*\(.*password|logger\.[a-z]+\s*\(.*token)", re.IGNORECASE),
        "Redact secrets in logs; use structured logging with field masks.",
        "Logging secrets spreads them to aggregators and support tickets.",
        "crypto-logging",
    ),
    (
        "Security Misconfiguration",
        "MEDIUM",
        "A05:2021 – Security Misconfiguration",
        "CWE-489",
        re.compile(r"(DEBUG\s*=\s*True|APP_DEBUG\s*=\s*true)", re.IGNORECASE),
        "Disable debug flags in production builds; enforce secure defaults via configuration baselines.",
        "Debug modes expose stack traces and weaken cookie/session protections.",
        "misconfig-debug",
    ),
    (
        "XML External Entity (XXE)",
        "HIGH",
        "A05:2021 – Security Misconfiguration",
        "CWE-611",
        re.compile(r"(XMLParser\s*\(|etree\.XML\s*\(|lxml\.etree\.parse\s*\()", re.IGNORECASE),
        "Disable external entities and DTD processing; use defusedxml or hardened parser settings.",
        "XXE lets attackers read local files and pivot through SSRF.",
        "misconfig-xxe",
    ),
    (
        "Broken Access Control",
        "HIGH",
        "A01:2021 – Broken Access Control",
        "CWE-639",
        re.compile(
            r"(is_admin\s*=\s*request\.(args|GET|POST)|role\s*=\s*request\.(args|GET))",
            re.IGNORECASE,
        ),
        "Derive authorization from server-side session claims, never from client-controlled parameters.",
        "Trusting query parameters for privilege checks lets attackers self-elevate roles.",
        "broken-access-params",
    ),
    (
        "Insufficient Logging & Monitoring",
        "LOW",
        "A09:2021 – Security Logging and Monitoring Failures",
        "CWE-778",
        re.compile(r"except\s*:\s*pass|except\s+Exception\s*:\s*pass", re.IGNORECASE),
        "Log security-relevant failures with correlation IDs; avoid silent swallow of broad exceptions.",
        "Silent failures hide brute-force attempts and exploitation traces during incident response.",
        "logging-monitoring",
    ),
]


def _lesson_url(base: str, lesson_slug: str) -> str:
    return f"{base.rstrip('/')}/lessons/{lesson_slug}"


def _iter_added_lines(diff: str) -> Iterator[tuple[int, str]]:
    """Yield (new_file_line, text) for added lines in a unified diff."""
    current_new = 0
    for raw in diff.splitlines():
        if raw.startswith("@@"):
            match = re.search(r"\+(\d+)(?:,(\d+))?", raw)
            if match:
                current_new = int(match.group(1))
            continue
        if raw.startswith("+++") or raw.startswith("---"):
            continue
        if not raw:
            continue
        prefix, body = raw[0], raw[1:]
        if prefix == "+":
            yield current_new, body
            current_new += 1
        elif prefix == " ":
            current_new += 1
        elif prefix == "-":
            continue


def _severity_rank(sev: str) -> int:
    order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "INFO": 0}
    return order.get(sev.upper(), 2)


def _overall_risk(issues: list[SecurityIssue]) -> str:
    if not issues:
        return "LOW"
    top = max((_severity_rank(i.severity) for i in issues), default=0)
    if top >= 4:
        return "HIGH"
    if top >= 3:
        return "HIGH"
    if top >= 2:
        return "MEDIUM"
    return "LOW"


class SecureCodingEducator:
    """Analyzes MR diffs, teaches secure patterns, and posts educational MR comments."""

    def __init__(
        self,
        connector: GitLabOrbitConnector,
        *,
        lesson_base_url: str | None = None,
    ) -> None:
        self._connector = connector
        self._lesson_base = lesson_base_url or os.environ.get(
            "TUTORIAL_LESSON_BASE",
            "https://tutorial.local/knowledge",
        )

    def _analyze_file(self, file_path: str, diff: str) -> list[SecurityIssue]:
        findings: list[SecurityIssue] = []
        for line_no, text in _iter_added_lines(diff):
            for name, severity, category, cwe, pattern, fix, edu, slug in _SECURITY_RULES:
                if pattern.search(text):
                    findings.append(
                        SecurityIssue(
                            file=file_path,
                            line=line_no,
                            severity=severity,
                            category=category,
                            description=f"{name} pattern detected in added line.",
                            fix_suggestion=fix,
                            educational_explanation=edu,
                            related_lesson_id=slug,
                            cwe_id=cwe,
                        )
                    )
        return findings

    def _build_snippets(self, issues: list[SecurityIssue]) -> list[LessonSnippet]:
        snippets: list[LessonSnippet] = []
        seen: set[str] = set()
        for issue in issues:
            key = issue.related_lesson_id or issue.category
            if key in seen:
                continue
            seen.add(key)
            url = (
                _lesson_url(self._lesson_base, issue.related_lesson_id)
                if issue.related_lesson_id
                else None
            )
            snippets.append(
                LessonSnippet(
                    title=f"Lesson hook: {issue.category}",
                    body_markdown=(
                        f"**Concept**: {issue.category}\n\n"
                        f"**Why it matters**: {issue.educational_explanation}\n\n"
                        f"**Try this fix**: {issue.fix_suggestion}"
                    ),
                    related_lesson_url=url,
                )
            )
        return snippets

    def _format_mr_comment(self, review: SecurityReview) -> str:
        lines = [
            "## TUTORIAL — Secure coding review",
            "",
            f"**Overall risk**: {review.overall_risk}",
            "",
            "### Findings",
            "",
        ]
        for issue in review.issues_found:
            lesson = (
                _lesson_url(self._lesson_base, issue.related_lesson_id)
                if issue.related_lesson_id
                else "_(internal knowledge base)_"
            )
            lines.extend(
                [
                    f"- **{issue.severity}** — `{issue.file}:{issue.line}` — {issue.category}",
                    f"  - {issue.description}",
                    f"  - **CWE**: {issue.cwe_id or 'n/a'}",
                    f"  - **Fix**: {issue.fix_suggestion}",
                    f"  - **Learn more**: {lesson}",
                    "",
                ]
            )
        if review.learning_opportunities:
            lines.extend(["### Learning opportunities", ""])
            for concept in review.learning_opportunities:
                lines.append(f"- {concept}")
            lines.append("")
        lines.append("_Generated by TUTORIAL GitLab integration (educational, not legal advice)._")
        return "\n".join(lines)

    async def review_and_teach(self, project_id: str, mr_iid: int) -> SecurityReview:
        changes = await self._connector.get_merge_request_changes(project_id, mr_iid)
        issues: list[SecurityIssue] = []
        for change in changes:
            new_path = str(change.get("new_path") or change.get("old_path") or "unknown")
            diff_text = str(change.get("diff") or "")
            issues.extend(self._analyze_file(new_path, diff_text))

        learning = sorted({i.category for i in issues})
        snippets = self._build_snippets(issues)
        risk = _overall_risk(issues)
        mr_id = f"{project_id}!{mr_iid}"
        review = SecurityReview(
            mr_id=mr_id,
            issues_found=issues,
            educational_content=snippets,
            overall_risk=risk,
            learning_opportunities=learning,
        )
        comment = self._format_mr_comment(review)
        await self._connector.comment_on_mr(project_id, mr_iid, comment)

        for issue in issues:
            if issue.severity.upper() in {"CRITICAL", "HIGH"}:
                continue
            await self._connector.create_issue(
                project_id,
                title=f"[Lesson] {issue.category} in {issue.file}",
                description=(
                    f"Interactive lesson opportunity from MR !{mr_iid}.\n\n"
                    f"**File**: `{issue.file}:{issue.line}`\n"
                    f"**Summary**: {issue.description}\n\n"
                    f"**Teaching notes**:\n{issue.educational_explanation}\n\n"
                    f"**Suggested fix**:\n```\n{issue.fix_suggestion}\n```\n"
                ),
                labels=["tutorial-lesson", "security-education", "non-blocking"],
            )

        logger.info("secure_review_posted", mr=mr_id, issues=len(issues))
        return review
