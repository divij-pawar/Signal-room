from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from signalroom.common.schemas import (
    CodeRef,
    Confidence,
    Coverage,
    Escalation,
    EvidenceRef,
    GuardianVerdict,
    RCAReport,
    Severity,
    TimeWindow,
    Verdict,
)

T0 = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
W = TimeWindow(start=T0, end=T0 + timedelta(minutes=4))


def verdict(v: Verdict, reporting: int = 3, **kw) -> GuardianVerdict:
    return GuardianVerdict(window=W, verdict=v, reason="r",
                           coverage=Coverage(hosts_expected=3, hosts_reporting=reporting), **kw)


def test_missing_data_cannot_be_ok():
    with pytest.raises(ValidationError, match="coverage is incomplete"):
        verdict(Verdict.OK, reporting=2)
    assert verdict(Verdict.UNKNOWN, reporting=2).verdict is Verdict.UNKNOWN


def test_extra_fields_are_rejected():
    data = verdict(Verdict.OK).model_dump(mode="json") | {"run_shell": "rm -rf /"}
    with pytest.raises(ValidationError):
        GuardianVerdict.model_validate(data)


def test_window_and_coverage_bounds():
    with pytest.raises(ValidationError):
        TimeWindow(start=T0, end=T0)
    with pytest.raises(ValidationError):
        Coverage(hosts_expected=2, hosts_reporting=3)


def test_only_escalate_becomes_escalation():
    with pytest.raises(ValidationError):
        Escalation(verdict=verdict(Verdict.OK), evidence_refs=[EvidenceRef(window=W)])
    esc = Escalation(verdict=verdict(Verdict.ESCALATE, trace_ids=["b", "a"]),
                     evidence_refs=[EvidenceRef(window=W)])
    assert esc.dedupe_key == "trace:a,b"


def test_rca_report_needs_real_severity_and_ordered_code_ref():
    base = dict(root_cause_service="payment", root_cause_category="config",
                root_cause="bad config", confidence=Confidence.HIGH)
    with pytest.raises(ValidationError):
        RCAReport(severity=Severity.NONE, **base)
    assert RCAReport(severity=Severity.SEV2, **base).severity is Severity.SEV2
    with pytest.raises(ValidationError):
        CodeRef(file="a.py", start_line=10, end_line=5)
