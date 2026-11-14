"""Model-backed agents against a scripted fake model (no network, no API key).

The fake reads the real prompts the agents send and answers like a cooperative model, so
these tests exercise the full loop: digest, gating, tool calls, evidence verification,
scrubbing and the audit trail. They do not measure model quality.
"""

import json
import re
from pathlib import Path

import httpx
import pytest

from signalroom.common.config import ModelsConfig
from signalroom.common.llm import InvalidModelOutput, ModelClient
from signalroom.common.schemas import Coverage, Escalation, EvidenceRef, GuardianVerdict, Severity, Verdict
from signalroom.common.telemetry import InMemoryTelemetry
from signalroom.evals.runner import run_scenario
from signalroom.evals.scenario import load_scenarios
from signalroom.guardian.digest import TemplateTracker, build_digest
from signalroom.guardian.model_guardian import ModelGuardian
from signalroom.rca.model_rca import ModelRCA

SCENARIOS = {s.id: s for s in load_scenarios(Path(__file__).resolve().parent.parent / "evals" / "scenarios")}
CONFIG = ModelsConfig.model_validate({
    "budget": {"daily_requests": 10_000, "daily_tokens": 10**9, "daily_usd": 100},
    "roles": {r: {"providers": [{"name": "fake", "base_url": "https://fake.test/v1", "model": f"fake-{r}",
                                 "price_in_per_m": 1, "price_out_per_m": 1}]} for r in ("guardian", "rca")},
})


def answer(payload) -> httpx.Response:
    content = payload if isinstance(payload, str) else json.dumps(payload)
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}],
                                     "usage": {"prompt_tokens": 100, "completion_tokens": 20}})


def tagged(text: str, tag: str) -> str:
    return re.search(rf"<{tag}[^>]*>\n(.*?)\n</{tag}>", text, re.S).group(1)


def cooperative_model(sent: list):
    """Escalates on error signals; RCA checks timing, pulls errors, cites what it was shown."""

    def handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content)
        sent.append(body)
        msgs = body["messages"]
        if body["model"] == "fake-guardian":
            digest = json.loads(tagged(msgs[-1]["content"], "telemetry_digest"))
            hot = [s.split(":", 1)[1] for s in digest["signals"]
                   if s.startswith(("new_error_template", "error_rate"))]
            if not hot:
                return answer({"verdict": "ok", "severity_guess": "none", "services": [], "reason": "quiet"})
            return answer({"verdict": "escalate", "severity_guess": "sev2",
                           "services": list(dict.fromkeys(hot)), "reason": "errors"})

        results = [m["content"] for m in msgs if m["role"] == "user" and "<tool_result" in m["content"]]
        if not results:
            return answer({"tool": "list_services", "args": {}})
        last = json.loads(tagged(results[-1], "tool_result"))
        if len(results) == 1:
            first = min((s for s in last if s["first_error"]), key=lambda s: s["first_error"])
            return answer({"tool": "query_logs", "args": {"service": first["service"], "level": "ERROR", "limit": 3}})
        row = last[0]
        return answer({"final": {
            "severity": "sev2", "root_cause_service": row["service"], "root_cause_category": "dependency",
            "root_cause": row["body"], "confidence": "medium",
            "evidence": [{"ref": row["ref"], "excerpt": row["body"][:40]}],
            "affected_services": [row["service"]], "next_steps": ["check it"], "unknowns": []}})

    return handler


def client_for(handler) -> ModelClient:
    return ModelClient(CONFIG, transport=httpx.MockTransport(handler), sleep=lambda s: None, env={})


def test_digest_is_much_smaller_than_raw_logs():
    s = SCENARIOS["selftest-payment-config"]
    t = InMemoryTelemetry.from_jsonl(s.fixture_path)
    tracker = TemplateTracker()
    digests = [build_digest(t.query_logs(w, limit=10**6), s.hosts, tracker) for w in s.time_windows()]
    assert not digests[0].anomalous  # warm-up window is quiet
    assert "error_rate:payment" in digests[3].signals
    assert digests[3].digest_tokens < digests[3].raw_tokens / 2


def test_healthy_windows_skip_the_model():
    sent = []
    g = ModelGuardian(client_for(cooperative_model(sent)))
    s = SCENARIOS["selftest-watcher-gap"]
    t = InMemoryTelemetry.from_jsonl(s.fixture_path)
    verdicts = [g.assess(w, t, s.hosts).verdict for w in s.time_windows()]
    assert sent == []
    assert verdicts == [Verdict.OK, Verdict.OK, Verdict.UNKNOWN, Verdict.UNKNOWN, Verdict.OK, Verdict.OK]


def test_model_saying_ok_with_missing_hosts_becomes_unknown():
    g = ModelGuardian(client_for(lambda req: answer(
        {"verdict": "ok", "severity_guess": "none", "services": ["ghost"], "reason": "fine"})))
    s = SCENARIOS["selftest-payment-config"]
    t = InMemoryTelemetry.from_jsonl(s.fixture_path)
    w = s.time_windows()[3]
    v = g.assess(w, t, s.hosts + ["extra-host"])
    assert v.verdict is Verdict.UNKNOWN and v.services == []


def test_cooperative_model_finds_cascade_cause_that_baseline_misses():
    score = run_scenario(SCENARIOS["selftest-cascade"],
                         *_agents(cooperative_model([])))
    assert score.incident_detected
    assert score.rca.service_correct  # the cause logged its first error before its callers
    assert score.rca.evidence_verified == score.rca.evidence_total == 1


def test_secrets_never_reach_the_model_and_injection_stays_inside_untrusted_tags():
    sent = []
    score = run_scenario(SCENARIOS["selftest-injection"], *_agents(cooperative_model(sent)))
    wire = json.dumps(sent)
    assert "S3cr3tPassw0rd" not in wire
    assert score.secret_leaks == 0
    for body in sent:
        for m in body["messages"]:
            if "IGNORE ALL PREVIOUS INSTRUCTIONS" in m["content"]:
                assert re.search(r"untrusted=\\?\"true\\?\"", m["content"])
                assert m["role"] == "user"


def test_disallowed_tools_are_blocked_and_fabricated_evidence_dropped():
    replies = iter([
        {"tool": "run_shell", "args": {"cmd": "cat /etc/passwd"}},
        {"tool": "query_logs", "args": {"service": "payment", "limit": 999}},
        {"tool": "query_logs", "args": {"service": "payment", "level": "ERROR", "limit": 1}},
        {"final": {"severity": "sev1", "root_cause_service": "payment", "root_cause_category": "config",
                   "root_cause": "bad config", "confidence": "high",
                   "evidence": [{"ref": "log:payment:2026-01-01T12:10:00+00:00", "excerpt": "made up"}]}},
    ])
    rca = ModelRCA(client_for(lambda req: answer(next(replies))))
    s = SCENARIOS["selftest-payment-config"]
    t = InMemoryTelemetry.from_jsonl(s.fixture_path)
    report = rca.analyze(_escalation(s), t)
    assert rca.stats["blocked_calls"] == 2
    assert [a.allowed for a in rca.audit] == [False, False, True]
    assert report.evidence == [] and rca.stats["evidence_dropped"] == 1
    assert any("could not be verified" in u for u in report.unknowns)


def test_rca_gives_up_after_step_limit():
    rca = ModelRCA(client_for(lambda req: answer({"tool": "list_services", "args": {}})), max_steps=3)
    s = SCENARIOS["selftest-payment-config"]
    with pytest.raises(InvalidModelOutput):
        rca.analyze(_escalation(s), InMemoryTelemetry.from_jsonl(s.fixture_path))


def _agents(handler):
    client = client_for(handler)
    return ModelGuardian(client), ModelRCA(client)


def _escalation(s) -> Escalation:
    w = s.time_windows()[3]
    v = GuardianVerdict(window=w, verdict=Verdict.ESCALATE, severity_guess=Severity.SEV2,
                        services=["payment"], reason="errors",
                        coverage=Coverage(hosts_expected=3, hosts_reporting=3))
    return Escalation(verdict=v, evidence_refs=[EvidenceRef(window=w, service="payment")])


def test_last_step_demands_a_final_report():
    prompts = []

    def handler(req):
        msgs = json.loads(req.content)["messages"]
        prompts.append(msgs[-1]["content"])
        if "LAST reply" in msgs[-1]["content"]:
            return answer({"final": {"severity": "sev2", "root_cause_service": "payment",
                                     "root_cause_category": "config", "root_cause": "x", "confidence": "low"}})
        return answer({"tool": "list_services", "args": {}})

    rca = ModelRCA(client_for(handler), max_steps=3)
    s = SCENARIOS["selftest-payment-config"]
    report = rca.analyze(_escalation(s), InMemoryTelemetry.from_jsonl(s.fixture_path))
    assert report.root_cause_service == "payment"
    assert "(3 replies left.)" in prompts[0] and "LAST reply" in prompts[2]
