"""Slack message construction (ARCHITECTURE.md section 3.5).

Builds the one-channel alert for Sev 1 and Sev 2 from an RCA report. Every text field is
secret-scrubbed here, at the last step before anything leaves the system.
"""

from __future__ import annotations

from signalroom.common.schemas import Escalation, RCAReport, Severity, SlackMessage
from signalroom.common.scrub import scrub

POSTED_SEVERITIES = {Severity.SEV1, Severity.SEV2}


def build_message(escalation: Escalation, report: RCAReport) -> SlackMessage:
    clean = lambda text: scrub(text).text  # noqa: E731
    return SlackMessage(
        severity=report.severity,
        affected_services=report.affected_services or escalation.verdict.services,
        root_cause=clean(report.root_cause),
        confidence=report.confidence,
        evidence_links=[clean(e.ref) for e in report.evidence],
        unknowns=[clean(u) for u in report.unknowns],
        dedupe_key=escalation.dedupe_key,
    )


def should_post(report: RCAReport) -> bool:
    return report.severity in POSTED_SEVERITIES


def render_text(msg: SlackMessage) -> str:
    """Plain-text rendering, the same text the UI previews."""
    lines = [
        f"[{msg.severity.value.upper()}] {', '.join(msg.affected_services) or 'unknown service'}",
        f"Root cause ({msg.confidence.value} confidence): {msg.root_cause}",
    ]
    if msg.evidence_links:
        lines.append("Evidence: " + ", ".join(msg.evidence_links))
    if msg.unknowns:
        lines.append("Unknowns: " + "; ".join(msg.unknowns))
    lines.append(f"Dedupe key: {msg.dedupe_key}")
    return "\n".join(lines)
