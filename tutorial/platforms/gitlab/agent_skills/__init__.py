"""GitLab Orbit-style skill modules for secure development education."""

from platforms.gitlab.agent_skills.code_review import CODE_REVIEW_SKILL
from platforms.gitlab.agent_skills.secure_practice import SECURE_PRACTICE_SKILL
from platforms.gitlab.agent_skills.vulnerability_scan import VULNERABILITY_SCAN_SKILL

__all__ = [
    "CODE_REVIEW_SKILL",
    "SECURE_PRACTICE_SKILL",
    "VULNERABILITY_SCAN_SKILL",
]
