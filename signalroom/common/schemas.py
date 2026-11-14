"""Data contracts shared by every component (ARCHITECTURE.md section 4).

Model output is validated against these before anything acts on it. Extra fields are
rejected so a model cannot smuggle in fields the pipeline does not expect.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Verdict(str, Enum):
    OK = "ok"
    ESCALATE = "escalate"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    SEV1 = "sev1"
    SEV2 = "sev2"
    SEV3 = "sev3"
    NONE = "none"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TimeWindow(Strict):
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def _ordered(self) -> TimeWindow:
        if self.end <= self.start:
            raise ValueError("window end must be after start")
        return self

    def contains(self, ts: datetime) -> bool:
        return self.start <= ts < self.end


class LogRecord(Strict):
    """One telemetry log record as Guardian and RCA see it."""

    timestamp: datetime
    host: str
    service: str
    severity_text: str = "INFO"
    body: str
    trace_id: str | None = None
    span_id: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class Coverage(Strict):
    hosts_expected: int = Field(ge=0)
    hosts_reporting: int = Field(ge=0)

    @model_validator(mode="after")
    def _bounded(self) -> Coverage:
        if self.hosts_reporting > self.hosts_expected:
            raise ValueError("hosts_reporting cannot exceed hosts_expected")
        return self

    @property
    def complete(self) -> bool:
        return self.hosts_reporting == self.hosts_expected


class GuardianVerdict(Strict):
    window: TimeWindow
    verdict: Verdict
    severity_guess: Severity = Severity.NONE
    services: list[str] = Field(default_factory=list)
    trace_ids: list[str] = Field(default_factory=list)
    reason: str = Field(max_length=1000)
    coverage: Coverage

    @model_validator(mode="after")
    def _missing_data_is_not_ok(self) -> GuardianVerdict:
        # Guardrail: missing data is reported as unknown, never as healthy.
        if self.verdict is Verdict.OK and not self.coverage.complete:
            raise ValueError("verdict cannot be ok when coverage is incomplete")
        return self


class EvidenceRef(Strict):
    """A pointer to evidence. Escalations carry references, never raw log bodies."""

    window: TimeWindow
    service: str | None = None
    trace_id: str | None = None


class Escalation(Strict):
    verdict: GuardianVerdict
    evidence_refs: list[EvidenceRef] = Field(min_length=1)

    @model_validator(mode="after")
    def _is_escalation(self) -> Escalation:
        if self.verdict.verdict is not Verdict.ESCALATE:
            raise ValueError("only an escalate verdict can become an escalation")
        return self

    @property
    def dedupe_key(self) -> str:
        traces = sorted(self.verdict.trace_ids)
        if traces:
            return "trace:" + ",".join(traces)
        services = ",".join(sorted(self.verdict.services))
        return f"window:{self.verdict.window.start.isoformat()}:{services}"


class Evidence(Strict):
    ref: str
    excerpt: str = Field(max_length=2000)


class CodeRef(Strict):
    file: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)

    @model_validator(mode="after")
    def _ordered(self) -> CodeRef:
        if self.end_line < self.start_line:
            raise ValueError("end_line must be >= start_line")
        return self


class RCAReport(Strict):
    trace_ids: list[str] = Field(default_factory=list)
    severity: Severity
    root_cause_service: str
    root_cause_category: str
    root_cause: str = Field(max_length=4000)
    confidence: Confidence
    evidence: list[Evidence] = Field(default_factory=list)
    code_refs: list[CodeRef] = Field(default_factory=list)
    affected_services: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _real_severity(self) -> RCAReport:
        if self.severity is Severity.NONE:
            raise ValueError("an RCA report must carry sev1, sev2 or sev3")
        return self


class SlackMessage(Strict):
    severity: Severity
    affected_services: list[str]
    root_cause: str
    confidence: Confidence
    evidence_links: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    dedupe_key: str
