"""Story arc construction from investigation steps with educational pacing."""

from __future__ import annotations

from collections.abc import Sequence

import structlog

from agents.teaching.tools.narrative_templates import (
    IncidentNarrativeTemplate,
    infer_incident_category,
    select_template,
)
from agents.teaching.narrative_types import (
    Character,
    Concept,
    Scene,
    Setting,
    Story,
    StoryArc,
    StoryArcType,
)
from shared.models import Incident, InvestigationStep

logger = structlog.get_logger(__name__)


def _step_summary(step: InvestigationStep) -> str:
    parts = [step.action_taken]
    if step.tool_used:
        parts.append(f"via {step.tool_used}")
    if step.interpretation:
        parts.append(f"— {step.interpretation}")
    if step.raw_output:
        parts.append(f"Evidence: {step.raw_output[:400]}")
    return " ".join(parts)


def _concepts_for_step(step: InvestigationStep) -> list[Concept]:
    text = f"{step.action_taken} {step.tool_used or ''} {step.interpretation or ''}".lower()
    concepts: list[Concept] = []
    if any(k in text for k in ("dns", "tunnel", "beacon")):
        concepts.append(
            Concept(
                id="dns_security",
                label="DNS as a covert channel",
                description="Attackers may tunnel data inside DNS queries because DNS is often allowed outbound.",
            ),
        )
    if any(k in text for k in ("memory", "volatility", "malfind", "injection")):
        concepts.append(
            Concept(
                id="memory_forensics",
                label="Memory forensics",
                description="Running processes and injected code in RAM reveal malware that hides on disk.",
            ),
        )
    if any(k in text for k in ("log", "auth", "4625", "brute")):
        concepts.append(
            Concept(
                id="log_correlation",
                label="Log correlation",
                description="Security logs sequenced in time show attacker behavior and blast radius.",
            ),
        )
    if any(k in text for k in ("network", "pcap", "traffic", "c2")):
        concepts.append(
            Concept(
                id="network_analysis",
                label="Network traffic analysis",
                description="Packets and flows expose command-and-control and data exfiltration patterns.",
            ),
        )
    if not concepts:
        concepts.append(
            Concept(
                id="incident_response",
                label="Structured incident response",
                description="Each investigation step documents hypotheses, tools, and findings for accountability.",
            ),
        )
    return concepts


class StoryEngine:
    """Maps real investigation steps to story beats with arc pacing."""

    def __init__(self, *, mentor_name: str = "Jordan Okonkwo") -> None:
        self._mentor_name = mentor_name

    def create_arc(
        self,
        investigation_steps: Sequence[InvestigationStep],
        incident: Incident,
        *,
        arc_type: StoryArcType | None = None,
        student_level: str = "beginner",
        template: IncidentNarrativeTemplate | None = None,
    ) -> StoryArc:
        """Build a five-part arc where every investigation step appears in rising or falling action."""

        category = infer_incident_category(incident)
        tpl = template or select_template(category)
        chosen_arc = arc_type or tpl.arc_type
        sorted_steps = sorted(investigation_steps, key=lambda s: s.timestamp)

        setting = Setting(
            location=tpl.default_setting_location,
            time_description="Moments after the security alert fires",
            mood="urgent" if incident.severity.value in ("high", "critical") else "focused",
            props=["analyst laptop", "SIEM dashboard", "evidence drive"],
        )

        mentor = Character(
            id="lead_analyst",
            name=self._mentor_name,
            role="mentor",
            personality="patient, precise, encourages structured thinking",
            knowledge_level="expert",
            dialogue_style="warm_professional",
            avatar_description="wears a SOC hoodie, headset, calm expression",
        )
        ai_agent = Character(
            id="investigation_agent",
            name="IRIS",
            role="guide",
            personality="methodical, cites evidence, transparent about confidence",
            knowledge_level="expert",
            dialogue_style="technical_plain_language",
            avatar_description="abstract holographic assistant avatar",
        )

        setup = Scene(
            id="scene_setup",
            title=tpl.setup_title,
            narrative_text=tpl.setup_narrative(incident),
            setting=setting,
            characters_present=[mentor, ai_agent],
            investigation_step_ref=None,
            concepts_demonstrated=[
                Concept(
                    id="alert_triage",
                    label="Alert triage",
                    description="Separating true incidents from noise using severity and corroboration.",
                ),
            ],
            interactive_element=None,
            next_scenes=["scene_rise_0"] if sorted_steps else ["scene_climax"],
            is_checkpoint=True,
        )

        rising: list[Scene] = []
        for idx, step in enumerate(sorted_steps):
            sid = f"scene_rise_{idx}"
            concepts = _concepts_for_step(step)
            narrative = (
                f"You open the analyst notebook to step {idx + 1}: {_step_summary(step)}. "
                f"As the lead detective, you decide what to trust first—timestamps, host context, or tool output."
            )
            rising.append(
                Scene(
                    id=sid,
                    title=f"Investigation beat: {step.action_taken}",
                    narrative_text=narrative,
                    setting=setting,
                    characters_present=[mentor, ai_agent],
                    investigation_step_ref=str(step.id),
                    concepts_demonstrated=concepts,
                    interactive_element=None,
                    next_scenes=[f"scene_rise_{idx + 1}"] if idx + 1 < len(sorted_steps) else ["scene_climax"],
                    is_checkpoint=idx % 2 == 0,
                ),
            )

        climax_detail = sorted_steps[-1] if sorted_steps else None
        climax_text = tpl.climax_narrative(incident, climax_detail)
        climax = Scene(
            id="scene_climax",
            title=tpl.climax_title,
            narrative_text=climax_text,
            setting=setting.model_copy(update={"mood": "revelatory"}),
            characters_present=[mentor, ai_agent],
            investigation_step_ref=str(climax_detail.id) if climax_detail else None,
            concepts_demonstrated=_concepts_for_step(climax_detail) if climax_detail else [Concept(id="impact", label="Impact", description="Understanding attacker impact.")],
            interactive_element=None,
            next_scenes=["scene_fall_0"],
            is_checkpoint=True,
        )

        falling: list[Scene] = []
        for j in range(min(2, max(1, len(sorted_steps) // 2 + 1))):
            falling.append(
                Scene(
                    id=f"scene_fall_{j}",
                    title="Containment and evidence integrity",
                    narrative_text=(
                        "You coordinate containment: preserve evidence hashes, isolate affected hosts, "
                        "and document decisions so legal and IT stakeholders stay aligned."
                    ),
                    setting=setting,
                    characters_present=[mentor],
                    investigation_step_ref=str(sorted_steps[-1 - j].id) if sorted_steps else None,
                    concepts_demonstrated=[
                        Concept(
                            id="chain_of_custody",
                            label="Chain of custody",
                            description="Every evidence transfer is logged to preserve admissibility and reproducibility.",
                        ),
                    ],
                    next_scenes=[f"scene_fall_{j + 1}"] if j == 0 and len(sorted_steps) > 1 else ["scene_resolution"],
                    is_checkpoint=False,
                ),
            )

        resolution = Scene(
            id="scene_resolution",
            title=tpl.resolution_title,
            narrative_text=tpl.resolution_narrative(incident, student_level),
            setting=setting.model_copy(update={"mood": "hopeful"}),
            characters_present=[mentor, ai_agent],
            investigation_step_ref=None,
            concepts_demonstrated=[
                Concept(
                    id="lessons_learned",
                    label="Lessons learned",
                    description="Post-incident improvements close gaps attackers exploited.",
                ),
            ],
            next_scenes=[],
            is_checkpoint=True,
        )

        return StoryArc(
            arc_type=chosen_arc,
            setup=setup,
            rising_action=rising,
            climax=climax,
            falling_action=falling,
            resolution=resolution,
        )

    def wrap_story(self, arc: StoryArc, incident: Incident, template: IncidentNarrativeTemplate) -> Story:
        """Attach synopsis and student-facing detective hook."""

        synopsis = (
            f"{template.marketing_logline} The case file follows real investigation actions from incident "
            f"“{incident.title}”. Students re-trace analyst decisions without inventing fake evidence."
        )
        hook = (
            "You are the lead detective: every clue in this story maps to a real SOC action. "
            "Question the AI partner, challenge assumptions, and win the case with evidence."
        )
        return Story(arc=arc, synopsis=synopsis, detective_hook=hook)
