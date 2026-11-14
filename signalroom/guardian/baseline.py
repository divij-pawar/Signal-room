"""Rule-based Guardian: the "no model" tier (ARCHITECTURE.md section 14.1).

It is both the cheapest Guardian and the baseline every model-backed Guardian must beat.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from signalroom.common.schemas import Coverage, GuardianVerdict, Severity, TimeWindow, Verdict
from signalroom.common.telemetry import Telemetry

ERROR_LEVELS = {"ERROR", "FATAL", "CRITICAL"}


@dataclass
class RuleGuardian:
    name: str = "rule-guardian"
    min_errors: int = 5
    error_ratio: float = 0.05

    def assess(self, window: TimeWindow, telemetry: Telemetry,
               hosts_expected: list[str]) -> GuardianVerdict:
        records = telemetry.query_logs(window, limit=1_000_000)
        reporting = {r.host for r in records} & set(hosts_expected)
        coverage = Coverage(hosts_expected=len(hosts_expected), hosts_reporting=len(reporting))

        totals = Counter(r.service for r in records)
        errors = Counter(r.service for r in records if r.severity_text.upper() in ERROR_LEVELS)
        hot = sorted(
            (s for s, n in errors.items() if n >= self.min_errors and n / totals[s] >= self.error_ratio),
            key=lambda s: -errors[s],
        )

        if hot:
            worst = max(errors[s] / totals[s] for s in hot)
            severity = Severity.SEV1 if worst >= 0.5 else Severity.SEV2 if worst >= 0.2 else Severity.SEV3
            traces = list(dict.fromkeys(
                r.trace_id for r in records
                if r.trace_id and r.service in hot and r.severity_text.upper() in ERROR_LEVELS
            ))[:5]
            reason = "error rate above threshold: " + ", ".join(
                f"{s} {errors[s]}/{totals[s]}" for s in hot)
            return GuardianVerdict(window=window, verdict=Verdict.ESCALATE, severity_guess=severity,
                                   services=hot, trace_ids=traces, reason=reason, coverage=coverage)

        if not coverage.complete:
            missing = sorted(set(hosts_expected) - reporting)
            return GuardianVerdict(window=window, verdict=Verdict.UNKNOWN, coverage=coverage,
                                   reason="no data from: " + ", ".join(missing))

        return GuardianVerdict(window=window, verdict=Verdict.OK, coverage=coverage,
                               reason="no service above the error threshold")
