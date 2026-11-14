"""Interfaces the pipeline and the eval harness drive. Model-backed and rule-based agents
both implement these, so the harness can compare them on the same scenarios."""

from __future__ import annotations

from typing import Protocol

from .schemas import Escalation, GuardianVerdict, RCAReport, TimeWindow
from .telemetry import Telemetry


class GuardianAgent(Protocol):
    name: str

    def assess(self, window: TimeWindow, telemetry: Telemetry,
               hosts_expected: list[str]) -> GuardianVerdict: ...


class RCAAgent(Protocol):
    name: str

    def analyze(self, escalation: Escalation, telemetry: Telemetry) -> RCAReport: ...
