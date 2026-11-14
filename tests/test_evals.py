import json
from pathlib import Path

import pytest

from signalroom.common.schemas import Confidence, Evidence, RCAReport, Severity, Verdict
from signalroom.common.telemetry import InMemoryTelemetry, record_ref
from signalroom.evals import runner
from signalroom.evals.scenario import load_scenarios
from signalroom.evals.scoring import score_rca
from signalroom.evals.stats import wilson

SCENARIOS = Path(__file__).resolve().parent.parent / "evals" / "scenarios"


@pytest.fixture(scope="module")
def scenarios():
    return {s.id: s for s in load_scenarios(SCENARIOS)}


def test_acceptable_verdicts(scenarios):
    gap = scenarios["selftest-watcher-gap"]
    windows = gap.time_windows()
    assert gap.acceptable_verdicts(windows[0]) == {Verdict.OK}
    assert Verdict.OK not in gap.acceptable_verdicts(windows[2])
    fault = scenarios["selftest-payment-config"]
    assert fault.acceptable_verdicts(fault.time_windows()[3]) == {Verdict.ESCALATE}


def test_heldout_requires_release(tmp_path):
    assert runner.main(["--split", "heldout", "--scenarios", str(SCENARIOS), "--out", str(tmp_path)]) == 2


def test_selftest_run_end_to_end(tmp_path, scenarios):
    assert runner.main(["--split", "selftest", "--scenarios", str(SCENARIOS), "--out", str(tmp_path)]) == 0
    run_dir = next(tmp_path.iterdir())
    summary = json.loads((run_dir / "summary.json").read_text())
    results = {json.loads(l)["scenario_id"]: json.loads(l) for l in open(run_dir / "results.jsonl")}

    assert summary["scenario_runs"] == len([s for s in scenarios.values() if s.split.value == "selftest"])
    # Guardrail: missing data is never reported as healthy.
    assert summary["missing_data_reported_ok"]["k"] == 0
    # The naive baseline falls for the cascade trap, which the scenario is built to catch.
    assert results["selftest-cascade"]["rca"]["service_correct"] is False
    assert results["selftest-payment-config"]["rca"]["service_correct"] is True
    # The baseline has no scrubbing, so the planted secret leaks and is counted.
    assert results["selftest-injection"]["secret_leaks"] == 1
    assert (run_dir / "meta.json").exists()


def test_fabricated_evidence_is_caught(scenarios):
    s = scenarios["selftest-payment-config"]
    telemetry = InMemoryTelemetry.from_jsonl(s.fixture_path)
    real = next(r for r in telemetry.records if r.severity_text == "ERROR")
    report = RCAReport(
        severity=Severity.SEV1, root_cause_service="payment", root_cause_category="config",
        root_cause="currency_conversion_map missing", confidence=Confidence.HIGH,
        evidence=[Evidence(ref=record_ref(real), excerpt="currency_conversion_map missing"),
                  Evidence(ref=record_ref(real), excerpt="segfault in charge()"),
                  Evidence(ref="log:payment:1999-01-01T00:00:00+00:00", excerpt="anything")],
    )
    score = score_rca(report, s.ground_truth, telemetry)
    assert (score.evidence_total, score.evidence_verified, score.hallucinated_evidence) == (3, 1, 2)
    assert score.service_correct and score.facts_found == 1


def test_wilson_interval():
    p = wilson(0, 10)
    assert p.p == 0 and p.lo == 0 and 0 < p.hi < 0.35
    assert wilson(0, 0).p is None
