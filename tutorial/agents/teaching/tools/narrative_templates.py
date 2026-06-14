"""Reusable narrative templates keyed by incident category."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from agents.teaching.narrative_types import StoryArcType
from config.constants import IncidentSeverity
from shared.models import Incident, InvestigationStep


@dataclass(frozen=True, slots=True)
class IncidentNarrativeTemplate:
    """Template metadata and narrative hooks for a class of incidents."""

    key: str
    arc_type: StoryArcType
    title: str
    marketing_logline: str
    default_setting_location: str
    setup_title: str
    climax_title: str
    resolution_title: str
    csta_standards: tuple[str, ...]
    setup_narrative_fn: Callable[[Incident], str]
    climax_narrative_fn: Callable[[Incident, InvestigationStep | None], str]
    resolution_narrative_fn: Callable[[Incident, str], str]

    def setup_narrative(self, incident: Incident) -> str:
        return self.setup_narrative_fn(incident)

    def climax_narrative(self, incident: Incident, step: InvestigationStep | None) -> str:
        return self.climax_narrative_fn(incident, step)

    def resolution_narrative(self, incident: Incident, student_level: str) -> str:
        return self.resolution_narrative_fn(incident, student_level)


def _setup_ransomware(inc: Incident) -> str:
    return (
        f"Encrypted extensions blink across finance shares for {inc.target_asset or 'the server room'}. "
        "A ransom note demands cryptocurrency, but your job starts with preserving volatile evidence."
    )


def _climax_ransomware(inc: Incident, step: InvestigationStep | None) -> str:
    detail = _step_summary_safe(step)
    return (
        "The forensic timeline converges: the adversary used a stolen credential hours before encryption. "
        f"Latest analyst finding: {detail} "
        "Immutable backups—not the ransom note—are the ethical path to recovery."
    )


def _resolution_ransomware(inc: Incident, level: str) -> str:
    depth = "Keep language concrete and define every acronym once." if level == "beginner" else "Invite students to compare tradeoffs between restore speed and verification depth."
    return (
        "Students document restore points, validate backup integrity, and patch the exposed service. "
        f"{depth} Emphasize that paying ransom does not guarantee decryption."
    )


def _setup_exfil(inc: Incident) -> str:
    return (
        "NetOps flags a spike in outbound DNS query sizes from a workstation that should only browse intranet sites. "
        "Something is leaking data quietly."
    )


def _climax_exfil(inc: Incident, step: InvestigationStep | None) -> str:
    detail = _step_summary_safe(step)
    return (
        "The exfiltration path snaps into focus: long-lived DNS queries carry encoded chunks to a look-alike domain. "
        f"Key evidence from the investigation: {detail}"
    )


def _resolution_exfil(inc: Incident, level: str) -> str:
    return (
        "Students block the sinkholed domain, rotate compromised credentials, and tune egress monitoring. "
        f"Difficulty framing for {level}: stress proportionality between blocking business traffic and containing leaks."
    )


def _setup_malware(inc: Incident) -> str:
    return (
        f"Help desk tickets describe sluggish laptops after users opened a spear-phishing attachment related to: {inc.title}. "
        "Memory captures are already en route to the lab."
    )


def _climax_malware(inc: Incident, step: InvestigationStep | None) -> str:
    detail = _step_summary_safe(step)
    return (
        "A suspicious process without a mapped file, odd parent-child relationships, and outbound beaconing line up. "
        f"The decisive analyst step: {detail}"
    )


def _resolution_malware(inc: Incident, level: str) -> str:
    return (
        "Students remove persistence, rebuild golden images if needed, and enable application controls. "
        f"For {level} learners, narrate why rebooting alone is insufficient if malware lives outside disk."
    )


def _setup_generic(inc: Incident) -> str:
    return (
        f"A {inc.severity.value} incident titled “{inc.title}” crosses your console. "
        f"Stakeholders echo the user report: {inc.description[:280]}..."
    )


def _climax_generic(inc: Incident, step: InvestigationStep | None) -> str:
    detail = _step_summary_safe(step)
    return (
        "Pieces align when analysts correlate host telemetry with authentication and network evidence. "
        f"The turning point in the real case: {detail}"
    )


def _resolution_generic(inc: Incident, level: str) -> str:
    return (
        "Students summarize indicators, propose monitoring improvements, and rehearse tabletop responses. "
        f"Pedagogical note for {level}: keep each technical claim tethered to a cited investigation artifact."
    )


def _step_summary_safe(step: InvestigationStep | None) -> str:
    if step is None:
        return "synthesized findings across preserved logs and host telemetry."
    parts = [step.action_taken]
    if step.interpretation:
        parts.append(step.interpretation[:400])
    return " ".join(parts)


RANSOMWARE_TEMPLATE = IncidentNarrativeTemplate(
    key="ransomware",
    arc_type=StoryArcType.MYSTERY,
    title="The Locked Files Mystery",
    marketing_logline="A classic ransomware storm tests backups, ethics, and nerves.",
    default_setting_location="Hybrid SOC / school cyber range",
    setup_title="The ransom note arrives",
    climax_title="Backups beat the ransom",
    resolution_title="Restore, patch, educate",
    csta_standards=("1B-AP-08", "2-AP-13", "3A-AP-15"),
    setup_narrative_fn=_setup_ransomware,
    climax_narrative_fn=_climax_ransomware,
    resolution_narrative_fn=_resolution_ransomware,
)

EXFIL_TEMPLATE = IncidentNarrativeTemplate(
    key="data_exfiltration",
    arc_type=StoryArcType.RACING_CLOCK,
    title="The Vanishing Data",
    marketing_logline="Quiet bytes slip out until students decode the exfiltration channel.",
    default_setting_location="Corporate NOC overlooking server racks",
    setup_title="The anomaly on the wire",
    climax_title="The hidden tunnel exposed",
    resolution_title="Stop the bleed, notify with care",
    csta_standards=("2-DA-07", "3B-AP-21", "3A-AP-15"),
    setup_narrative_fn=_setup_exfil,
    climax_narrative_fn=_climax_exfil,
    resolution_narrative_fn=_resolution_exfil,
)

MALWARE_TEMPLATE = IncidentNarrativeTemplate(
    key="malware",
    arc_type=StoryArcType.DEEP_DIVE,
    title="The Silent Intruder",
    marketing_logline="Students peel back layers of persistence and deception.",
    default_setting_location="University SOC lab",
    setup_title="The help desk storm",
    climax_title="Malware unmasked",
    resolution_title="Eradicate and harden",
    csta_standards=("2-AP-13", "3A-AP-15", "3B-AP-20"),
    setup_narrative_fn=_setup_malware,
    climax_narrative_fn=_climax_malware,
    resolution_narrative_fn=_resolution_malware,
)

GENERIC_TEMPLATE = IncidentNarrativeTemplate(
    key="generic",
    arc_type=StoryArcType.WHODUNIT,
    title="The Case File",
    marketing_logline="A faithful walkthrough of a real investigation with no invented exploits.",
    default_setting_location="Cyber range classroom",
    setup_title="The alert lands",
    climax_title="Attribution tightens",
    resolution_title="What we learned",
    csta_standards=("1B-AP-08", "2-AP-11", "3A-AP-15"),
    setup_narrative_fn=_setup_generic,
    climax_narrative_fn=_climax_generic,
    resolution_narrative_fn=_resolution_generic,
)


def infer_incident_category(incident: Incident) -> str:
    """Infer a coarse category from incident text and severity."""

    blob = f"{incident.title} {incident.description}".lower()
    if any(w in blob for w in ("ransom", "encrypt", "locked files", "bitcoin")):
        return "ransomware"
    if any(w in blob for w in ("exfil", "dns tunnel", "data theft", "leak", "stolen data")):
        return "data_exfiltration"
    if any(w in blob for w in ("malware", "trojan", "payload", "malfind", "injection", "virus")):
        return "malware"
    if incident.severity == IncidentSeverity.CRITICAL and "dns" in blob:
        return "data_exfiltration"
    return "generic"


def select_template(category: str) -> IncidentNarrativeTemplate:
    """Pick the strongest template match."""

    return {
        "ransomware": RANSOMWARE_TEMPLATE,
        "data_exfiltration": EXFIL_TEMPLATE,
        "malware": MALWARE_TEMPLATE,
    }.get(category, GENERIC_TEMPLATE)
