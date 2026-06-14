"""GitLab Orbit-style skill: teach secure coding from concrete snippets."""

from __future__ import annotations

from platforms.gitlab.agent_skills.code_review import OrbitAgentSkill

SECURE_PRACTICE_SKILL = OrbitAgentSkill(
    slug="gitlab-orbit-secure-practice-coach",
    display_name="Secure Coding Practice Coach",
    system_prompt=(
        "Teach secure coding practices by analyzing code patterns and suggesting improvements. "
        "Ground guidance in OWASP Top 10 themes and defensive defaults. When proposing rewrites, "
        "show a secure alternative and explain the threat model difference in plain language."
    ),
    tools=[
        "tutorial.lesson_database.match_patterns",
        "security.pattern_matcher.python",
        "security.pattern_matcher.javascript",
    ],
    input_description="Focused code snippet plus optional language/runtime context.",
    output_description=(
        "Secure alternative implementation, checklist of hardening steps, and links to TUTORIAL "
        "lesson topics that deepen understanding."
    ),
)
