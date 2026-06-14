"""CSTA K-12 standards database and mapping utilities."""

from __future__ import annotations

import difflib
from collections import deque


from agents.teaching.education_models import CoverageReport, CSTAStandard, LessonContent


def _std(
    sid: str,
    category: str,
    grade_band: str,
    description: str,
    keywords: list[str],
) -> CSTAStandard:
    return CSTAStandard(
        id=sid,
        category=category,
        grade_band=grade_band,
        description=description,
        keywords=keywords,
    )


_CSTA_STANDARDS: list[CSTAStandard] = [
    _std(
        "DA-6-8-1",
        "DA",
        "6-8",
        "Collect data using computational tools and systematically extract information from data sources.",
        ["data", "collection", "dataset", "logs", "analysis", "forensics"],
    ),
    _std(
        "DA-9-12-2",
        "DA",
        "9-12",
        "Refine computational models based on the data they generate.",
        ["model", "inference", "visualization", "metrics", "correlation"],
    ),
    _std(
        "CS-6-8-1",
        "CS",
        "6-8",
        "Recommend improvements to the design of computing devices based on an analysis of how users interact with the devices.",
        ["hardware", "software", "systems", "process", "troubleshoot"],
    ),
    _std(
        "NI-6-8-1",
        "NI",
        "6-8",
        "Explain how protocols enable devices to send and receive information.",
        ["network", "protocol", "tcp", "udp", "packet", "dns", "http"],
    ),
    _std(
        "NI-9-12-2",
        "NI",
        "9-12",
        "Illustrate how sensitive information can be affected by the design and use of computing systems and networks.",
        ["encryption", "privacy", "data transmission", "tls", "vpn"],
    ),
    _std(
        "CY-6-8-1",
        "CY",
        "6-8",
        "Identify physical and digital security measures that protect electronic information.",
        ["malware", "threat", "protection", "authentication", "password", "phishing"],
    ),
    _std(
        "CY-9-12-3",
        "CY",
        "9-12",
        "Evaluate the tradeoffs between usability and security when recommending cybersecurity controls.",
        ["encryption", "privacy", "risk", "controls", "incident response"],
    ),
    _std(
        "IC-6-8-1",
        "IC",
        "6-8",
        "Discuss issues raised by computing practices such as equity, access, and influence on society.",
        ["ethics", "bias", "accessibility", "social impact", "responsible disclosure"],
    ),
    _std(
        "IC-9-12-1",
        "IC",
        "9-12",
        "Evaluate the impact of computing technologies on equity, access, and influence in a global society.",
        ["ethics", "policy", "compliance", "privacy law", "accessibility"],
    ),
    _std(
        "AP-6-8-1",
        "AP",
        "6-8",
        "Design algorithms that combine sequencing, selection, and iteration.",
        ["algorithm", "automation", "script", "problem solving", "debugging"],
    ),
    _std(
        "AP-9-12-2",
        "AP",
        "9-12",
        "Create computational artifacts using computing tools and techniques to solve problems by developing and modifying algorithms.",
        ["programming", "automation", "scripting", "tooling", "cli"],
    ),
]

_PREREQ: dict[str, list[str]] = {
    "DA-9-12-2": ["DA-6-8-1"],
    "NI-9-12-2": ["NI-6-8-1"],
    "CY-9-12-3": ["CY-6-8-1", "NI-6-8-1"],
    "IC-9-12-1": ["IC-6-8-1"],
    "AP-9-12-2": ["AP-6-8-1"],
}


class CSTAMapper:
    """Maps cybersecurity concepts to CSTA standards with traceable metadata."""

    def __init__(self, standards: list[CSTAStandard] | None = None) -> None:
        self._standards = standards or list(_CSTA_STANDARDS)
        self._by_id = {s.id: s for s in self._standards}

    @property
    def standards(self) -> list[CSTAStandard]:
        return list(self._standards)

    def find_standards(self, concepts: list[str], grade_band: str) -> list[CSTAStandard]:
        """Fuzzy-match concept strings to standards in the given grade band."""
        band = grade_band.strip()
        pool = [s for s in self._standards if s.grade_band == band]
        if not pool:
            pool = list(self._standards)
        matches: dict[str, float] = {}
        for concept in concepts:
            c = concept.lower().strip()
            if not c:
                continue
            for std in pool:
                score = 0.0
                for kw in std.keywords:
                    ratio = difflib.SequenceMatcher(None, c, kw.lower()).ratio()
                    if kw.lower() in c or c in kw.lower():
                        score = max(score, 0.92)
                    score = max(score, ratio * 0.85)
                if std.description.lower() in c or c in std.description.lower():
                    score = max(score, 0.88)
                if score > 0.45:
                    prev = matches.get(std.id, 0.0)
                    matches[std.id] = max(prev, score)
        ordered = sorted(matches.items(), key=lambda kv: kv[1], reverse=True)
        return [self._by_id[i] for i, _ in ordered if i in self._by_id]

    def get_prerequisites(self, standard_id: str) -> list[str]:
        return list(_PREREQ.get(standard_id, []))

    def get_learning_path(self, target_standards: list[str]) -> list[str]:
        """Topological order of prerequisites then targets (deduplicated)."""
        seen: set[str] = set()
        order: list[str] = []
        q: deque[str] = deque()

        for tid in target_standards:
            if tid in self._by_id:
                q.append(tid)

        prereq_stack: list[str] = []

        def visit(node: str) -> None:
            if node in seen:
                return
            for p in self.get_prerequisites(node):
                visit(p)
            if node not in seen:
                seen.add(node)
                prereq_stack.append(node)

        while q:
            n = q.popleft()
            visit(n)

        for sid in prereq_stack:
            if sid not in order:
                order.append(sid)
        for tid in target_standards:
            if tid in self._by_id and tid not in order:
                order.append(tid)
        return order

    def validate_coverage(self, lesson: LessonContent) -> CoverageReport:
        mapped: set[str] = set()
        unmapped: list[str] = []
        for concept in lesson.concept_labels:
            hits_912 = self.find_standards([concept], "9-12")
            hits_68 = self.find_standards([concept], "6-8")
            combined = hits_912 or hits_68
            if not combined:
                unmapped.append(concept)
            for std in hits_912 + hits_68:
                mapped.add(std.id)
        fully_mapped = len(unmapped) == 0
        return CoverageReport(
            fully_mapped=fully_mapped,
            unmapped_concepts=unmapped,
            standards_count=len(mapped),
        )
