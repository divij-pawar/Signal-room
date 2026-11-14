"""Naive RCA baseline: blame the loudest service.

This is deliberately simple. It is the number a model-backed RCA agent has to beat, and it
fails on cascades and misleading errors, which is exactly what the scenario set probes.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from signalroom.common.schemas import (
    Confidence,
    Escalation,
    Evidence,
    RCAReport,
    Severity,
    TimeWindow,
)
from signalroom.common.telemetry import Telemetry, record_ref
from signalroom.guardian.baseline import ERROR_LEVELS

CATEGORY_KEYWORDS = [
    ("config", ("config", "configuration", "missing key", "invalid setting")),
    ("resource", ("out of memory", "oom", "disk full", "no space left", "cpu")),
    ("dependency", ("timeout", "timed out", "connection refused", "unavailable", "deadline")),
]


def guess_category(text: str) -> str:
    lowered = text.lower()
    for category, words in CATEGORY_KEYWORDS:
        if any(w in lowered for w in words):
            return category
    return "unknown"


@dataclass
class LoudestServiceRCA:
    name: str = "loudest-service-rca"

    def analyze(self, escalation: Escalation, telemetry: Telemetry) -> RCAReport:
        windows = [ref.window for ref in escalation.evidence_refs]
        span = TimeWindow(start=min(w.start for w in windows), end=max(w.end for w in windows))
        errors = [r for r in telemetry.query_logs(span, limit=1_000_000)
                  if r.severity_text.upper() in ERROR_LEVELS]
        if not errors:
            return RCAReport(
                severity=escalation.verdict.severity_guess
                if escalation.verdict.severity_guess is not Severity.NONE else Severity.SEV3,
                root_cause_service="unknown", root_cause_category="unknown",
                root_cause="No error records found in the escalated window.",
                confidence=Confidence.LOW, unknowns=["no error records in escalated window"])

        counts = Counter(r.service for r in errors)
        service, _ = counts.most_common(1)[0]
        examples = [r for r in errors if r.service == service][:3]
        category = guess_category(" ".join(r.body for r in examples))
        severity = escalation.verdict.severity_guess
        if severity is Severity.NONE:
            severity = Severity.SEV3
        return RCAReport(
            trace_ids=escalation.verdict.trace_ids,
            severity=severity,
            root_cause_service=service,
            root_cause_category=category,
            root_cause=f"{service} logged the most errors ({counts[service]}): {examples[0].body}",
            confidence=Confidence.LOW,
            evidence=[Evidence(ref=record_ref(r), excerpt=r.body[:300]) for r in examples],
            affected_services=[s for s, _ in counts.most_common()],
            next_steps=[f"Inspect recent changes and dependencies of {service}."],
        )
