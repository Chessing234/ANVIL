"""GitLab Orbit-style skill: security-focused merge request review."""

from __future__ import annotations

from pydantic import BaseModel, Field


class OrbitAgentSkill(BaseModel):
    """Declarative Orbit skill contract for agent runtimes."""

    model_config = {"extra": "forbid"}

    slug: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    system_prompt: str = Field(min_length=1)
    tools: list[str] = Field(default_factory=list)
    input_description: str = Field(min_length=1)
    output_description: str = Field(min_length=1)


CODE_REVIEW_SKILL = OrbitAgentSkill(
    slug="gitlab-orbit-security-code-review",
    display_name="Security Code Review (GitLab MR)",
    system_prompt=(
        "You are a security-focused code reviewer. Analyze code for vulnerabilities and provide "
        "educational feedback. Prefer evidence-backed findings: cite CWE/OWASP categories, reference "
        "safe patterns, and avoid speculative claims without code support. When uncertain, say what "
        "additional context would be required."
    ),
    tools=[
        "gitlab_api.merge_request_changes",
        "gitlab_api.merge_request_notes",
        "tutorial.knowledge_base.search_lessons",
        "security.cwe_lookup",
    ],
    input_description="Unified diff or MR IID plus project identifier for fetching changes.",
    output_description=(
        "Structured review: severity-ordered findings, OWASP mapping, educational explanations, "
        "and concrete fix snippets suitable for a GitLab MR comment."
    ),
)
