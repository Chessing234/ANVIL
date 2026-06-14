"""Interactive learning elements and factory for investigation-driven lessons."""

from __future__ import annotations

from collections.abc import Sequence


from agents.teaching.narrative_types import (
    AnyInteractiveElement,
    Choice,
    ChoicePoint,
    DiscoveryMoment,
    Puzzle,
    PuzzleType,
    ReflectionPrompt,
)
from shared.models import InvestigationStep, StudentProfile


class InteractiveElementsFactory:
    """Creates varied interactives aligned to real investigation content."""

    def __init__(self, student: StudentProfile) -> None:
        self._student = student
        self._last_kind: str | None = None

    def _next_kind(self, desired: str) -> str:
        if self._last_kind == desired:
            rotation = ("choice_point", "puzzle", "discovery_moment", "reflection_prompt")
            idx = (rotation.index(desired) + 1) % len(rotation)
            desired = rotation[idx]
        self._last_kind = desired
        return desired

    def _hints(self, base: list[str]) -> list[str]:
        if self._student.experience_level == "beginner":
            return base + ["Compare timestamps across two artifacts.", "Look for impossible geography in IPs."]
        return base

    def build_for_investigation(
        self,
        steps: Sequence[InvestigationStep],
        scene_ids: Sequence[str],
    ) -> dict[str, AnyInteractiveElement]:
        """Map scene ids to interactives; ensures variety across consecutive scenes."""

        mapping: dict[str, AnyInteractiveElement] = {}
        sorted_steps = sorted(steps, key=lambda s: s.timestamp)
        if not scene_ids:
            return mapping

        first_id = scene_ids[0]
        self._next_kind("choice_point")
        mapping[first_id] = ChoicePoint(
            id=f"{first_id}_choice",
            question="What is the safest first move when ransomware is suspected?",
            choices=[
                Choice(id="a", label="Isolate and preserve evidence", description="Stop spread, image RAM if possible."),
                Choice(id="b", label="Pay the ransom immediately", description="Risky and not guaranteed."),
                Choice(id="c", label="Reboot everything", description="May destroy volatile evidence."),
            ],
            correct_choice_id="a",
            explanation_correct="Isolation protects peers while preserving disks and memory for forensics.",
            explanation_incorrect={
                "b": "Payment does not ensure decryption and may fund crime.",
                "c": "Reboots can wipe memory-only malware artifacts.",
            },
            concept_tested="incident_triage",
        )

        for idx, step in enumerate(sorted_steps):
            if idx + 1 >= len(scene_ids):
                break
            sid = scene_ids[idx + 1]
            text = f"{step.action_taken} {step.tool_used or ''} {step.interpretation or ''}".lower()
            if "log" in text or "4625" in text or "auth" in text:
                desired = "puzzle"
            elif "dns" in text or "network" in text or "traffic" in text:
                desired = "discovery_moment"
            else:
                desired = "reflection_prompt"
            desired = self._next_kind(desired)
            if desired == "puzzle":
                mapping[sid] = Puzzle(
                    id=f"{sid}_puzzle",
                    puzzle_type=PuzzleType.LOG_ANALYSIS,
                    description="Given the excerpt, identify the anomaly that suggests credential abuse.",
                    data_provided=(step.raw_output or "2024-06-01T12:00:01Z auth fail user=svc_web ip=203.0.113.7")[:1800],
                    solution="Repeated failures from distributed IPs against one service account.",
                    hints=self._hints(["Sort by user then by IP.", "Count failures per 5-minute bucket."]),
                    expected_answer="credential_stuffing",
                    validation_logic="normalize answer lower; accept 'credential stuffing' or 'password_spray'",
                )
            elif desired == "discovery_moment":
                mapping[sid] = DiscoveryMoment(
                    id=f"{sid}_discovery",
                    build_up="You align DNS query entropy with process creation telemetry.",
                    reveal=f"The investigation record highlights: {step.interpretation or step.action_taken}",
                    technical_explanation=(
                        "DNS tunneling encodes data in subdomain labels; defenders look at length, entropy, and volume "
                        "against benign baselines."
                    ),
                    visual_description="A waterfall chart of query lengths spikes at the same hour processes spawn.",
                    emotional_beat="The pattern clicks—this was never random noise.",
                )
            else:
                mapping[sid] = ReflectionPrompt(
                    id=f"{sid}_reflect",
                    question="Why might attackers prefer DNS for exfiltration in a locked-down enterprise?",
                    guidance="Think about default-allowed egress and encryption blind spots.",
                    sample_good_answer="DNS is often allowed outbound and inspection may be shallow compared to HTTPS proxies.",
                    concept_reinforced="network_security",
                )

        return mapping

    def collect_flat(self, mapping: dict[str, AnyInteractiveElement]) -> list[AnyInteractiveElement]:
        """Flatten interactives for ``NarrativeResult`` summary."""

        return list(mapping.values())

    def collect_flat_ordered(
        self,
        mapping: dict[str, AnyInteractiveElement],
        scene_ids: Sequence[str],
    ) -> list[AnyInteractiveElement]:
        """Return interactives in scene order for predictable lesson authoring."""

        return [mapping[sid] for sid in scene_ids if sid in mapping]
