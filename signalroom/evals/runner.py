"""Eval runner (EVALS.md section 14).

Replays each scenario's recorded telemetry window by window through a Guardian agent,
hands the first escalation to an RCA agent, scores both mechanically, and writes
results to runs/<run_id>/. The held-out split only runs with --release.

    python -m signalroom.evals.runner --split selftest
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from signalroom.common.agents import GuardianAgent, RCAAgent
from signalroom.common.config import load_config
from signalroom.common.env import load_dotenv
from signalroom.common.llm import BudgetExceeded, CallRecord, InvalidModelOutput, ModelClient, ModelUnavailable
from signalroom.common.schemas import (
    Coverage,
    Escalation,
    EvidenceRef,
    GuardianVerdict,
    Verdict,
)
from signalroom.common.telemetry import InMemoryTelemetry
from signalroom.guardian import model_guardian
from signalroom.guardian.baseline import RuleGuardian
from signalroom.guardian.model_guardian import ModelGuardian
from signalroom.rca import model_rca
from signalroom.rca.baseline import LoudestServiceRCA
from signalroom.rca.model_rca import ModelRCA

from .scenario import Scenario, Split, load_scenarios
from .scoring import (
    ScenarioScore,
    count_secret_leaks,
    score_rca,
    score_windows,
)
from .stats import median, wilson

GUARDIANS = ["rule", "model"]
RCAS = ["loudest", "model"]


def make_agents(guardian: str, rca: str, client: ModelClient | None) -> tuple[GuardianAgent, RCAAgent]:
    """Fresh agents per scenario run, so per-run state (templates seen, audit, stats) never leaks."""
    g = RuleGuardian() if guardian == "rule" else ModelGuardian(client)
    r = LoudestServiceRCA() if rca == "loudest" else ModelRCA(client)
    return g, r


def run_scenario(scenario: Scenario, guardian: GuardianAgent, rca: RCAAgent,
                 repeat: int = 0) -> ScenarioScore:
    telemetry = InMemoryTelemetry.from_jsonl(scenario.fixture_path)
    score = ScenarioScore(scenario_id=scenario.id, repeat=repeat, split=scenario.split.value,
                          family=scenario.family, difficulty=scenario.difficulty.value)

    verdicts = []
    for window in scenario.time_windows():
        try:
            v = guardian.assess(window, telemetry, scenario.hosts)
        except (ModelUnavailable, InvalidModelOutput) as e:
            score.schema_failures += isinstance(e, InvalidModelOutput)
            v = GuardianVerdict(window=window, verdict=Verdict.UNKNOWN,
                                coverage=Coverage(hosts_expected=len(scenario.hosts), hosts_reporting=0),
                                reason=f"guardian unavailable: {type(e).__name__}")
        verdicts.append((window, v))

    score.windows, score.incident_detected, score.detection_latency_s = score_windows(scenario, verdicts)

    first = next((v for _, v in verdicts if v.verdict is Verdict.ESCALATE), None)
    if first is None:
        return score

    refs = [EvidenceRef(window=first.window, service=s) for s in first.services] or \
        [EvidenceRef(window=first.window)]
    escalation = Escalation(verdict=first, evidence_refs=refs)
    try:
        report = rca.analyze(escalation, telemetry)
    except (ModelUnavailable, InvalidModelOutput) as e:
        score.schema_failures += isinstance(e, InvalidModelOutput)
        score.no_rca_reason = type(e).__name__
        return score

    score.secret_leaks = count_secret_leaks(report.model_dump_json(), scenario.ground_truth)
    if scenario.has_fault:
        score.rca = score_rca(report, scenario.ground_truth, telemetry)
    return score


def summarize(scores: list[ScenarioScore]) -> dict:
    windows = [w for s in scores for w in s.windows]
    healthy = [w for w in windows if w.gold == "ok"]
    gaps = [w for w in windows if w.gold == "unknown"]
    faults = [s for s in scores if s.incident_detected is not None]
    rcas = [s.rca for s in scores if s.rca]
    evidence_total = sum(r.evidence_total for r in rcas)
    code = [r.code_ref_correct for r in rcas if r.code_ref_correct is not None]
    facts_req = sum(r.facts_required for r in rcas)
    g_stats = [s.agent_stats.get("guardian", {}) for s in scores]
    r_stats = [s.agent_stats.get("rca", {}) for s in scores]
    windows_seen = sum(g.get("windows", 0) for g in g_stats)
    cited = sum(r.get("evidence_cited", 0) for r in r_stats)
    dropped = sum(r.get("evidence_dropped", 0) for r in r_stats)
    called_raw = sum(g.get("raw_tokens", 0) for g in g_stats)
    fault_tokens = [s.tokens_in + s.tokens_out for s in faults]

    return {
        "model_calls": sum(s.model_calls for s in scores),
        "tokens_in": sum(s.tokens_in for s in scores),
        "tokens_out": sum(s.tokens_out for s in scores),
        "cost_usd_estimate": round(sum(s.cost_usd for s in scores), 6),
        "tokens_per_incident_mean": sum(fault_tokens) / len(fault_tokens) if fault_tokens else None,
        "guardian_windows_without_model_call": wilson(
            sum(g.get("model_calls_skipped", 0) for g in g_stats), windows_seen).as_dict(),
        "guardian_digest_vs_raw_tokens": (
            {"raw": called_raw, "digest": sum(g.get("digest_tokens", 0) for g in g_stats)}
            if windows_seen else None),
        "failed_model_calls": sum(sum(s.agent_stats.get("call_errors", {}).values()) for s in scores),
        "rca_blocked_tool_calls": sum(r.get("blocked_calls", 0) for r in r_stats),
        "rca_invalid_replies": sum(r.get("invalid_replies", 0) for r in r_stats),
        "raw_evidence_faithfulness": wilson(cited - dropped, cited).as_dict(),

        "scenario_runs": len(scores),
        "window_accuracy": wilson(sum(w.correct for w in windows), len(windows)).as_dict(),
        "incident_recall": wilson(sum(bool(s.incident_detected) for s in faults), len(faults)).as_dict(),
        "detection_latency_median_s": median(
            [s.detection_latency_s for s in faults if s.detection_latency_s is not None]),
        "false_escalation_rate": wilson(sum(w.predicted == "escalate" for w in healthy), len(healthy)).as_dict(),
        "missing_data_reported_ok": wilson(sum(w.predicted == "ok" for w in gaps), len(gaps)).as_dict(),
        "rca_service_top1": wilson(sum(r.service_correct for r in rcas), len(rcas)).as_dict(),
        "rca_category": wilson(sum(r.category_correct for r in rcas), len(rcas)).as_dict(),
        "rca_severity": wilson(sum(r.severity_correct for r in rcas), len(rcas)).as_dict(),
        "evidence_faithfulness": wilson(sum(r.evidence_verified for r in rcas), evidence_total).as_dict(),
        "code_ref_accuracy": wilson(sum(code), len(code)).as_dict(),
        "fact_coverage": wilson(sum(r.facts_found for r in rcas), facts_req).as_dict(),
        "no_rca": sum(1 for s in scores if s.no_rca_reason),
        "schema_failures": sum(s.schema_failures for s in scores),
        "secret_leaks": sum(s.secret_leaks for s in scores),
        "confusion": dict(Counter(f"{w.gold}->{w.predicted}" for w in windows)),
    }


def _fmt(p: dict) -> str:
    if not p["n"]:
        return "n/a (n=0)"
    lo, hi = p["ci95"]
    return f"{p['p']:6.1%}  [{lo:.1%}, {hi:.1%}]  ({p['k']}/{p['n']})"


def print_summary(summary: dict, run_id: str, reportable: bool) -> None:
    print(f"\nRun {run_id}" + ("" if reportable else "  (selftest: synthetic, not reportable)"))
    rows = [
        ("Window accuracy", _fmt(summary["window_accuracy"])),
        ("Incident recall", _fmt(summary["incident_recall"])),
        ("Detection latency (median)", f"{summary['detection_latency_median_s']} s"
         if summary["detection_latency_median_s"] is not None else "n/a"),
        ("False escalations (healthy windows)", _fmt(summary["false_escalation_rate"])),
        ("Missing data reported ok", _fmt(summary["missing_data_reported_ok"])),
        ("RCA root-cause service (top-1)", _fmt(summary["rca_service_top1"])),
        ("RCA category", _fmt(summary["rca_category"])),
        ("RCA severity", _fmt(summary["rca_severity"])),
        ("Evidence faithfulness", _fmt(summary["evidence_faithfulness"])),
        ("Code-ref accuracy", _fmt(summary["code_ref_accuracy"])),
        ("Fact coverage", _fmt(summary["fact_coverage"])),
        ("No-RCA runs", str(summary["no_rca"])),
        ("Schema failures", str(summary["schema_failures"])),
        ("Secret leaks", str(summary["secret_leaks"])),
        ("Model calls (failed)", f"{summary['model_calls']} ({summary['failed_model_calls']})"),
        ("Guardian windows without a model call", _fmt(summary["guardian_windows_without_model_call"])),
        ("Tokens per incident (mean)", f"{summary['tokens_per_incident_mean']:.0f}"
         if summary["tokens_per_incident_mean"] is not None else "n/a"),
        ("Estimated cost (list price)", f"${summary['cost_usd_estimate']:.4f}"),
        ("RCA blocked tool calls", str(summary["rca_blocked_tool_calls"])),
        ("Raw evidence faithfulness (before verifier)", _fmt(summary["raw_evidence_faithfulness"])),
    ]
    width = max(len(r[0]) for r in rows)
    for name, value in rows:
        print(f"  {name:<{width}}  {value}")
    print("  Confusion (gold->predicted): " +
          ", ".join(f"{k}: {v}" for k, v in sorted(summary["confusion"].items())))


def _key_problems(config) -> list[str]:
    """Catch the common mistakes without ever printing a key value."""
    problems = []
    for role, rc in config.roles.items():
        for p in rc.providers:
            env = p.api_key_env
            if env is None:
                continue
            if env.startswith(("sk-", "sk_")) or len(env) > 64:
                problems.append(f"{role}/{p.name}: api_key_env looks like a key, not a variable name. "
                                "Put the key in .env and set api_key_env to the variable's name.")
            elif not os.environ.get(env):
                problems.append(f"{role}/{p.name}: environment variable {env} is not set (shell or .env)")
    return problems


def _split_hashes(scenarios: list[Scenario]) -> dict[str, str]:
    by_split: dict = {}
    for s in sorted(scenarios, key=lambda s: s.id):
        h = by_split.setdefault(s.split.value, hashlib.sha256())
        h.update(s.path.read_bytes() if s.path else s.id.encode())
        h.update(s.fixture_path.read_bytes())
    return {k: v.hexdigest()[:16] for k, v in by_split.items()}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run Signal Room evals over recorded scenarios.")
    ap.add_argument("--scenarios", default="evals/scenarios")
    ap.add_argument("--split", action="append", choices=[s.value for s in Split],
                    help="split to run (repeatable); default: dev")
    ap.add_argument("--release", action="store_true", help="required to run the heldout split")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--guardian", choices=GUARDIANS, default="rule")
    ap.add_argument("--rca", choices=RCAS, default="loudest")
    ap.add_argument("--config", default="config/models.yaml", help="model config (for model agents)")
    ap.add_argument("--max-usd", type=float, help="spend cap for this run; overrides the config budget")
    ap.add_argument("--out", default="runs")
    args = ap.parse_args(argv)

    splits = {Split(s) for s in (args.split or ["dev"])}
    if Split.HELDOUT in splits and not args.release:
        print("refusing to run the heldout split without --release", file=sys.stderr)
        return 2

    scenarios = [s for s in load_scenarios(args.scenarios) if s.split in splits]
    if not scenarios:
        print(f"no scenarios in splits {sorted(s.value for s in splits)}", file=sys.stderr)
        return 1

    calls: list[CallRecord] = []
    client = None
    models = {}
    if "model" in (args.guardian, args.rca):
        if not Path(args.config).exists():
            print(f"model config {args.config} not found; copy config/models.example.yaml "
                  "and export OPENROUTER_API_KEY", file=sys.stderr)
            return 1
        load_dotenv()
        config = load_config(args.config)
        if problems := _key_problems(config):
            print("model config problem:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 1
        if args.max_usd is not None:
            config.budget.daily_usd = args.max_usd
        client = ModelClient(config, recorder=calls.append)
        models = {role: [f"{p.name}:{p.model}" for p in rc.providers] for role, rc in config.roles.items()}

    started = datetime.now(timezone.utc)
    meta = {
        "started_at": started.isoformat(),
        "splits": sorted(s.value for s in splits),
        "split_hashes": _split_hashes(scenarios),
        "agents": {
            "guardian": args.guardian if args.guardian == "rule" else
            {"name": "model-guardian", "prompt": model_guardian.PROMPT_VERSION, "models": models.get("guardian")},
            "rca": args.rca if args.rca == "loudest" else
            {"name": "model-rca", "prompt": model_rca.PROMPT_VERSION, "models": models.get("rca")},
        },
        "repeats": args.repeats,
        "scenarios": [s.id for s in scenarios],
    }
    config_hash = hashlib.sha256(json.dumps(meta, sort_keys=True, default=str).encode()).hexdigest()[:8]
    run_id = f"{started:%Y%m%dT%H%M%SZ}-{config_hash}"

    scores = []
    for s in scenarios:
        for r in range(args.repeats):
            calls.clear()
            guardian, rca = make_agents(args.guardian, args.rca, client)
            score = run_scenario(s, guardian, rca, r)
            score.model_calls = len(calls)
            score.tokens_in = sum(c.tokens_in for c in calls)
            score.tokens_out = sum(c.tokens_out for c in calls)
            score.cost_usd = sum(c.cost_usd for c in calls)
            score.agent_stats = {"guardian": getattr(guardian, "stats", {}), "rca": getattr(rca, "stats", {}),
                                 "rca_audit": [vars(a) for a in getattr(rca, "audit", [])],
                                 "call_errors": dict(Counter(f"{c.role}/{c.model}: {c.error}"
                                                             for c in calls if not c.ok))}
            scores.append(score)
    if client is not None:
        try:
            client.budget.check()
        except BudgetExceeded as e:
            print(f"warning: budget hit during the run ({e}); later model calls were skipped", file=sys.stderr)
    summary = summarize(scores)

    out = Path(args.out) / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    with open(out / "results.jsonl", "w") as f:
        for s in scores:
            f.write(json.dumps(s.as_dict()) + "\n")

    print_summary(summary, run_id, reportable=Split.SELFTEST not in splits)
    print(f"\n  Results written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
