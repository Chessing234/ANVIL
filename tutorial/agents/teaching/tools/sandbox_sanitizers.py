"""Reversible sanitization pipeline for sandbox artifacts (no real PII or malware)."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SanitizationLogEntry:
    """Single reversible replacement for instructor audit."""

    step: str
    original_fragment: str
    replacement_fragment: str
    context: str = ""
    entry_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


class SanitizationAudit:
    """Accumulates all sanitization steps for a sandbox build."""

    def __init__(self) -> None:
        self.entries: list[SanitizationLogEntry] = []

    def log(self, step: str, original: str, replacement: str, context: str = "") -> None:
        self.entries.append(
            SanitizationLogEntry(
                step=step,
                original_fragment=original,
                replacement_fragment=replacement,
                context=context,
            ),
        )

    def reverse_for_review(self, text: str) -> str:
        """Apply inverse mapping (replacement -> original) for instructor review only."""

        out = text
        for e in reversed(self.entries):
            out = out.replace(e.replacement_fragment, e.original_fragment, 1)
        return out


_IPV4 = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b",
)


class IPAnonymizer:
    """Map public-looking IPs to RFC 5737 documentation space (192.0.2.0/24)."""

    def __init__(self, audit: SanitizationAudit) -> None:
        self._audit = audit
        self._counter = 1
        self._mapping: dict[str, str] = {}

    def sanitize(self, text: str) -> str:
        def repl(m: re.Match[str]) -> str:
            ip = m.group(0)
            if ip.startswith("192.0.2."):
                return ip
            if ip in self._mapping:
                return self._mapping[ip]
            doc = f"192.0.2.{min(self._counter, 254)}"
            self._counter += 1
            self._mapping[ip] = doc
            self._audit.log("ip_anonymizer", ip, doc)
            return doc

        return _IPV4.sub(repl, text)


_HOSTISH = re.compile(r"\b(?:[a-z0-9-]+\.)+(?:local|corp|internal|lan)\b", re.I)


class HostnameAnonymizer:
    """Replace obvious internal hostnames with fictional labels."""

    def __init__(self, audit: SanitizationAudit) -> None:
        self._audit = audit
        self._idx = 1

    def sanitize(self, text: str) -> str:

        def repl(m: re.Match[str]) -> str:
            orig = m.group(0)
            fake = f"lab-{self._idx}.example.invalid"
            self._idx += 1
            self._audit.log("hostname_anonymizer", orig, fake)
            return fake

        return _HOSTISH.sub(repl, text)


_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_SSN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CC = re.compile(r"\b(?:\d[ -]*?){13,16}\b")


class PIIRedactor:
    """Redact common PII patterns."""

    def __init__(self, audit: SanitizationAudit) -> None:
        self._audit = audit

    def sanitize(self, text: str) -> str:
        out = text

        def redact_email(m: re.Match[str]) -> str:
            self._audit.log("pii_redactor", m.group(0), "[REDACTED_EMAIL]")
            return "[REDACTED_EMAIL]"

        def redact_ssn(m: re.Match[str]) -> str:
            self._audit.log("pii_redactor", m.group(0), "[REDACTED_SSN]")
            return "[REDACTED_SSN]"

        def redact_cc(m: re.Match[str]) -> str:
            self._audit.log("pii_redactor", m.group(0), "[REDACTED_PAN]")
            return "[REDACTED_PAN]"

        out = _EMAIL.sub(redact_email, out)
        out = _SSN.sub(redact_ssn, out)
        out = _CC.sub(redact_cc, out)
        return out


_MALWAREISH = re.compile(
    r"\b(?:payload|shellcode|meterpreter|cobalt|beacon|stager)\b[\s:=]+([A-Za-z0-9+/=._-]{16,})",
    re.I,
)


class MalwareNeutralizer:
    """Replace suspicious binary-looking blobs with benign placeholders."""

    def __init__(self, audit: SanitizationAudit) -> None:
        self._audit = audit

    def sanitize(self, text: str) -> str:

        def repl(m: re.Match[str]) -> str:
            orig = m.group(0)
            digest = hashlib.sha256(orig.encode("utf-8", errors="replace")).hexdigest()[:16]
            benign = f"SANITIZED_BENIGN_PLACEHOLDER_{digest}.txt"
            self._audit.log("malware_neutralizer", orig, benign, context="high_entropy_replaced")
            return benign

        return _MALWAREISH.sub(repl, text)


class LogSanitizer:
    """Anonymize usernames and internal-looking paths in log-like text."""

    def __init__(self, audit: SanitizationAudit) -> None:
        self._audit = audit

    def sanitize(self, text: str) -> str:
        out = text
        user_pat = re.compile(r"\b(?:user|uid|login)[:=]\s*([A-Za-z0-9._-]{3,32})\b", re.I)

        def urepl(m: re.Match[str]) -> str:
            orig_user = m.group(1)
            fake = f"user_{uuid.uuid4().hex[:6]}"
            self._audit.log("log_sanitizer", orig_user, fake, context="username")
            sep = ":" if ":" in m.group(0) else "="
            key = m.group(0).split(sep)[0].rstrip()
            return f"{key}{sep}{fake}"

        out = user_pat.sub(urepl, out)
        path_pat = re.compile(r"(/Users/|/home/|C:\\Users\\)([A-Za-z0-9._-]+)")

        def prepl(m: re.Match[str]) -> str:
            orig = m.group(0)
            fake = f"{m.group(1)}learner_sandbox"
            self._audit.log("log_sanitizer", orig, fake, context="path")
            return fake

        out = path_pat.sub(prepl, out)
        return out


def run_full_pipeline(text: str, audit: SanitizationAudit | None = None) -> tuple[str, SanitizationAudit]:
    """Run all sanitizers in a fixed order."""

    a = audit or SanitizationAudit()
    pipeline: list[Any] = [
        IPAnonymizer(a),
        HostnameAnonymizer(a),
        PIIRedactor(a),
        MalwareNeutralizer(a),
        LogSanitizer(a),
    ]
    out = text
    for step in pipeline:
        out = step.sanitize(out)
    return out, a
