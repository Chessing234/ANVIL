"""Hypothesis lifecycle: create, test, merge, prune, rank, and alternatives."""

from __future__ import annotations

import re
from collections import defaultdict

from shared.models import Evidence, Hypothesis, HypothesisResult, HypothesisState, Incident


class HypothesisManager:
    """Manages investigative hypotheses from creation through confirmation or rejection."""

    _EMAIL_RE = re.compile(r"\b(phish|spear|email|smtp|outlook)\b", re.I)
    _NET_RE = re.compile(r"\b(dns|beacon|c2|exfil|pcap|traffic)\b", re.I)
    _MAL_RE = re.compile(r"\b(malware|ransom|trojan|inject|malfind)\b", re.I)
    _CRED_RE = re.compile(r"\b(credential|brute|password|spray)\b", re.I)

    def create_initial(self, incident: Incident) -> list[Hypothesis]:
        """Generate 3–5 ranked hypotheses from incident text and severity."""

        text = f"{incident.title} {incident.description}".lower()
        seeds: list[tuple[str, str, float]] = []
        if self._EMAIL_RE.search(text):
            seeds.append(
                (
                    "Initial access via malicious email attachment or link",
                    "Incident language references email or phishing vectors.",
                    0.55,
                ),
            )
        if self._NET_RE.search(text):
            seeds.append(
                (
                    "Command-and-control or data exfiltration over the network (including DNS tunneling)",
                    "Network or DNS indicators referenced in incident metadata.",
                    0.58,
                ),
            )
        if self._MAL_RE.search(text):
            seeds.append(
                (
                    "In-memory malware or code injection on the affected host",
                    "Memory or malware keywords present in incident narrative.",
                    0.52,
                ),
            )
        if self._CRED_RE.search(text):
            seeds.append(
                (
                    "Credential theft or brute-force leading to follow-on activity",
                    "Authentication abuse language detected.",
                    0.5,
                ),
            )
        seeds.append(
            (
                "Benign misconfiguration or operational noise misclassified as malicious",
                "Null hypothesis to force falsification against evidence.",
                0.25,
            ),
        )
        if len(seeds) < 3:
            seeds.extend(
                [
                    (
                        "Lateral movement via remote access tools",
                        "Default coverage when incident details are sparse.",
                        0.45,
                    ),
                    (
                        "Supply-chain or trusted-path compromise",
                        "Secondary advanced scenario.",
                        0.35,
                    ),
                ],
            )
        ranked = sorted(seeds, key=lambda s: s[2], reverse=True)[:5]
        return [
            Hypothesis(text=t, rationale=r, confidence=c, state=HypothesisState.CREATED)
            for t, r, c in ranked
        ]

    def test(self, hypothesis: Hypothesis, evidence: list[Evidence]) -> HypothesisResult:
        """Score a hypothesis against collected evidence using lightweight rules."""

        supporting: list[str] = []
        contradicting: list[str] = []
        h = hypothesis.text.lower()
        for ev in evidence:
            meta = " ".join(str(v) for v in ev.metadata.values()).lower()
            if ev.type == "log_file" and ("auth" in h or "brute" in h or "credential" in h):
                if "fail" in meta or "4625" in meta:
                    supporting.append(f"log:{ev.id}:auth_failures")
                if "success" in meta and "4672" in meta:
                    supporting.append(f"log:{ev.id}:privileged_logon")
            if ev.type == "network_capture" and ("network" in h or "dns" in h or "exfil" in h):
                if "beacon" in meta or "tunnel" in meta or "dns" in meta:
                    supporting.append(f"pcap:{ev.id}:suspicious_network_pattern")
                if meta.count("normal") > 2:
                    contradicting.append(f"pcap:{ev.id}:benign_pattern_markers")
            if ev.type == "memory_dump" and ("memory" in h or "inject" in h or "malware" in h):
                if "injection" in meta or "malfind" in meta or "anomal" in meta:
                    supporting.append(f"mem:{ev.id}:injection_or_anomaly")
                if "baseline" in meta and "injection" not in meta:
                    contradicting.append(f"mem:{ev.id}:weak_memory_signals")
            if ev.type == "disk_image" and "lateral" in h:
                if "rdp" in meta or "ps1" in meta:
                    supporting.append(f"disk:{ev.id}:script_or_rdp_artifact")
            if "benign" in h and ev.type == "log_file":
                if "fail" in meta:
                    contradicting.append(f"log:{ev.id}:shows_hostile_auth_noise")

        raw = (len(supporting) - len(contradicting)) * 0.18 + hypothesis.confidence
        score = max(0.0, min(1.0, raw))
        return HypothesisResult(hypothesis_id=hypothesis.id, supporting=supporting, contradicting=contradicting, score=score)

    def merge(self, hypotheses: list[Hypothesis]) -> list[Hypothesis]:
        """Combine hypotheses that share substantive wording."""

        buckets: dict[str, list[Hypothesis]] = defaultdict(list)
        for hyp in hypotheses:
            key = " ".join(sorted(set(hyp.text.lower().split())))[:120]
            buckets[key].append(hyp)
        merged: list[Hypothesis] = []
        for group in buckets.values():
            if len(group) == 1:
                merged.append(group[0])
                continue
            best = max(group, key=lambda h: h.confidence)
            others = [h for h in group if h.id != best.id]
            rationale = best.rationale + " Merged with related hypotheses: " + "; ".join(h.text for h in others)
            merged.append(
                best.model_copy(
                    update={
                        "rationale": rationale[:5000],
                        "confidence": min(1.0, best.confidence + 0.05),
                        "state": HypothesisState.MERGED if best.state != HypothesisState.CONFIRMED else best.state,
                    },
                ),
            )
        return merged

    def prune(self, hypotheses: list[Hypothesis], threshold: float = 0.3) -> list[Hypothesis]:
        """Remove hypotheses below ``threshold`` confidence."""

        return [h for h in hypotheses if h.confidence >= threshold]

    def rank(self, hypotheses: list[Hypothesis]) -> list[Hypothesis]:
        """Sort hypotheses by descending confidence."""

        return sorted(hypotheses, key=lambda h: h.confidence, reverse=True)

    def get_alternatives(self, failed_hypothesis: Hypothesis) -> list[Hypothesis]:
        """Generate fresh hypotheses when a primary theory fails."""

        base = failed_hypothesis.text.lower()
        alts: list[Hypothesis] = []
        if "email" in base:
            alts.append(
                Hypothesis(
                    text="Network-based staging without email — review DNS and long TLS sessions",
                    rationale="Email vector unsupported; pivot to pure network forensics.",
                    confidence=0.42,
                    state=HypothesisState.CREATED,
                ),
            )
        if "network" in base or "dns" in base:
            alts.append(
                Hypothesis(
                    text="Host-local persistence and scheduled tasks driving callbacks",
                    rationale="Network-only narrative insufficient; examine disk and autoruns.",
                    confidence=0.4,
                    state=HypothesisState.CREATED,
                ),
            )
        alts.append(
            Hypothesis(
                text="Insider misuse of legitimate admin tools (living-off-the-land)",
                rationale="Fallback when malware artifacts are weak but privileged activity exists.",
                confidence=0.38,
                state=HypothesisState.CREATED,
            ),
        )
        alts.append(
            Hypothesis(
                text="Automated scanner or red-team activity mistaken for adversary",
                rationale="Alternative benign explanation after failed high-confidence match.",
                confidence=0.33,
                state=HypothesisState.CREATED,
            ),
        )
        return alts[:4]

    @staticmethod
    def mark_state(hypothesis: Hypothesis, state: HypothesisState) -> Hypothesis:
        """Return a copy with updated lifecycle state."""

        return hypothesis.model_copy(update={"state": state})

    @staticmethod
    def apply_result(hypothesis: Hypothesis, result: HypothesisResult) -> Hypothesis:
        """Update hypothesis confidence and state from a test result."""

        confirmed = result.score >= 0.55
        rejected = result.score < 0.3
        state = HypothesisState.CONFIRMED if confirmed else HypothesisState.REJECTED if rejected else HypothesisState.TESTING
        return hypothesis.model_copy(update={"confidence": result.score, "state": state})
