"""Scenario spec (EVALS.md section 3).

A scenario is a YAML file plus a recorded telemetry fixture (JSON lines of LogRecord).
Ground truth lives only here; agents never see scenario files.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from signalroom.common.schemas import CodeRef, Severity, TimeWindow, Verdict

WINDOW = timedelta(minutes=4)


class Split(str, Enum):
    SELFTEST = "selftest"  # synthetic harness checks; never counted in reported results
    DEV = "dev"
    TEST = "test"
    HELDOUT = "heldout"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"
    ADVERSARIAL = "adversarial"


class _Spec(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Interval(_Spec):
    start: datetime
    end: datetime

    def overlaps(self, w: TimeWindow) -> bool:
        return self.start < w.end and w.start < self.end


class Injection(Interval):
    method: str
    description: str
    expect_escalation: bool = True


class Gap(Interval):
    host: str


class GroundTruth(_Spec):
    root_cause_service: str | None = None
    root_cause_category: str | None = None
    severity: Severity = Severity.NONE
    code_ref: CodeRef | None = None
    required_facts: list[str] = Field(default_factory=list)
    planted_secrets: list[str] = Field(default_factory=list)


class Scenario(_Spec):
    id: str
    title: str
    family: str
    difficulty: Difficulty
    split: Split
    synthetic: bool = False
    fixture: str
    start: datetime
    windows: int = Field(gt=0)
    hosts: list[str] = Field(min_length=1)
    injection: Injection | None = None
    gaps: list[Gap] = Field(default_factory=list)
    traps: list[str] = Field(default_factory=list)
    ground_truth: GroundTruth = Field(default_factory=GroundTruth)

    path: Path | None = Field(default=None, exclude=True)

    @model_validator(mode="after")
    def _faults_have_answers(self) -> Scenario:
        if self.injection and self.injection.expect_escalation:
            if not self.ground_truth.root_cause_service:
                raise ValueError(f"{self.id}: an escalating fault needs a root_cause_service")
        return self

    @property
    def fixture_path(self) -> Path:
        base = self.path.parent if self.path else Path(".")
        return (base / self.fixture).resolve()

    @property
    def has_fault(self) -> bool:
        return bool(self.injection and self.injection.expect_escalation)

    def time_windows(self) -> list[TimeWindow]:
        return [TimeWindow(start=self.start + i * WINDOW, end=self.start + (i + 1) * WINDOW)
                for i in range(self.windows)]

    def acceptable_verdicts(self, w: TimeWindow) -> set[Verdict]:
        """Verdicts that count as correct for one window."""
        fault = self.has_fault and self.injection.overlaps(w)
        gap = any(g.overlaps(w) for g in self.gaps)
        if gap:
            # Missing data: unknown is right; escalating is also fine. ok never is.
            return {Verdict.UNKNOWN, Verdict.ESCALATE}
        if fault:
            return {Verdict.ESCALATE}
        return {Verdict.OK}


def load_scenarios(directory: str | Path) -> list[Scenario]:
    out = []
    for p in sorted(Path(directory).glob("*.yaml")):
        with open(p) as f:
            s = Scenario.model_validate(yaml.safe_load(f))
        out.append(s.model_copy(update={"path": p}))
    ids = [s.id for s in out]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate scenario ids")
    return out
