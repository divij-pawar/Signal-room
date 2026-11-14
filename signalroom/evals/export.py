"""Export replay bundles for the UI (docs/UI.md section 3).

Runs scenarios through the real agents and writes, per scenario, everything the UI replays:
scrubbed logs, per-window verdicts, the escalation, the RCA report, the Slack preview, the
tool-call audit, model calls and scores. An index file carries the run summary.

Published bundles never contain secrets: log bodies are scrubbed before they are written.

    python -m signalroom.evals.export --split selftest --out ui/public/demo-data
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from signalroom.common.config import load_config
from signalroom.common.env import load_dotenv
from signalroom.common.llm import CallRecord, ModelClient
from signalroom.common.scrub import scrub
from signalroom.common.telemetry import InMemoryTelemetry, record_ref
from signalroom.guardian.digest import INSTRUCTION_LIKE, level_of
from signalroom.notifier.slack import build_message, render_text, should_post

from .runner import GUARDIANS, RCAS, _key_problems, make_agents, run_scenario, summarize
from .scenario import Scenario, Split, load_scenarios

BUNDLE_VERSION = 1


class _WindowProbe:
    """Wraps a Guardian to note, per window, whether the model was actually called."""

    def __init__(self, guardian, calls: list[CallRecord]):
        self._g, self._calls = guardian, calls
        self.name = guardian.name
        self.model_called: list[bool] = []

    @property
    def stats(self):
        return getattr(self._g, "stats", {})

    def assess(self, window, telemetry, hosts):
        before = sum(1 for c in self._calls if c.role == "guardian")
        try:
            return self._g.assess(window, telemetry, hosts)
        finally:
            self.model_called.append(sum(1 for c in self._calls if c.role == "guardian") > before)


def _iso(dt) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def export_scenario(s: Scenario, guardian_kind: str, rca_kind: str, client: ModelClient | None,
                    calls: list[CallRecord]) -> tuple[dict, object]:
    calls.clear()
    guardian, rca = make_agents(guardian_kind, rca_kind, client)
    probe = _WindowProbe(guardian, calls)
    trace: dict = {}
    score = run_scenario(s, probe, rca, trace=trace)
    score.model_calls = len(calls)
    score.tokens_in = sum(c.tokens_in for c in calls)
    score.tokens_out = sum(c.tokens_out for c in calls)
    score.cost_usd = sum(c.cost_usd for c in calls)
    score.agent_stats = {"guardian": dict(probe.stats), "rca": dict(getattr(rca, "stats", {}))}

    telemetry = InMemoryTelemetry.from_jsonl(s.fixture_path)
    redactions: Counter[str] = Counter()
    logs, flagged = [], []
    for r in telemetry.records:
        cleaned = scrub(r.body)
        redactions.update(cleaned.counts)
        ref = record_ref(r)
        if INSTRUCTION_LIKE.search(r.body):
            flagged.append(ref)
        logs.append({"ref": ref, "t": _iso(r.timestamp), "host": r.host, "service": r.service,
                     "level": level_of(r), "body": cleaned.text, "trace_id": r.trace_id,
                     "redacted": cleaned.redacted > 0})

    audit = [vars(a) for a in getattr(rca, "audit", [])]
    incident = None
    esc, report = trace.get("escalation"), trace.get("report")
    if esc is not None:
        slack = None
        if report is not None:
            msg = build_message(esc, report)
            slack = {"posted": should_post(report), "message": msg.model_dump(mode="json"),
                     "text": render_text(msg)}
        incident = {
            "escalation": {"window_start": _iso(esc.verdict.window.start), "window_end": _iso(esc.verdict.window.end),
                           "services": esc.verdict.services, "trace_ids": esc.verdict.trace_ids,
                           "severity_guess": esc.verdict.severity_guess.value, "reason": esc.verdict.reason,
                           "dedupe_key": esc.dedupe_key},
            "report": json.loads(scrub(report.model_dump_json()).text) if report else None,
            "no_rca_reason": score.no_rca_reason,
            "rca_latency_s": trace.get("rca_latency_s"),
            "slack": slack,
            "audit": audit,
        }

    bundle = {
        "version": BUNDLE_VERSION,
        "scenario": {
            "id": s.id, "title": s.title, "family": s.family, "difficulty": s.difficulty.value,
            "split": s.split.value, "synthetic": s.synthetic, "hosts": s.hosts,
            "start": _iso(s.start), "windows": s.windows,
            "injection": s.injection and {"start": _iso(s.injection.start), "end": _iso(s.injection.end),
                                          "method": s.injection.method, "description": s.injection.description},
            "gaps": [{"host": g.host, "start": _iso(g.start), "end": _iso(g.end)} for g in s.gaps],
            "traps": s.traps,
        },
        "ground_truth": json.loads(scrub(s.ground_truth.model_dump_json(exclude={"planted_secrets"})).text)
        | {"planted_secrets": len(s.ground_truth.planted_secrets)},
        "logs": logs,
        "windows": [
            {"start": _iso(v.window.start), "end": _iso(v.window.end), "verdict": v.verdict.value,
             "severity_guess": v.severity_guess.value, "services": v.services, "trace_ids": v.trace_ids,
             "reason": scrub(v.reason).text, "hosts_expected": v.coverage.hosts_expected,
             "hosts_reporting": v.coverage.hosts_reporting, "model_called": called,
             "gold": w.gold, "correct": w.correct}
            for v, called, w in zip(trace["verdicts"], probe.model_called, score.windows)
        ],
        "incident": incident,
        "calls": [{"role": c.role, "provider": c.provider, "model": c.model, "t": _iso(c.started_at),
                   "ok": c.ok, "status": c.status, "error": c.error, "tokens_in": c.tokens_in,
                   "tokens_out": c.tokens_out, "latency_s": round(c.latency_s, 3),
                   "cost_usd": c.cost_usd, "redactions": c.redactions} for c in calls],
        "guardrails": {
            "redactions": dict(redactions),
            "instruction_like_refs": flagged,
            "blocked_tool_calls": [a for a in audit if not a["allowed"]],
            "redactions_before_model": sum(c.redactions for c in calls),
        },
        "score": score.as_dict(),
    }
    return bundle, score


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Export replay bundles for the UI.")
    ap.add_argument("--scenarios", default="evals/scenarios")
    ap.add_argument("--split", action="append", choices=[s.value for s in Split])
    ap.add_argument("--guardian", choices=GUARDIANS, default="rule")
    ap.add_argument("--rca", choices=RCAS, default="loudest")
    ap.add_argument("--config", default="config/models.yaml")
    ap.add_argument("--out", default="ui/public/demo-data")
    args = ap.parse_args(argv)

    splits = {Split(s) for s in (args.split or ["selftest"])}
    if Split.HELDOUT in splits:
        print("the heldout split is never exported", file=sys.stderr)
        return 2
    scenarios = [s for s in load_scenarios(args.scenarios) if s.split in splits]

    calls: list[CallRecord] = []
    client, models = None, {}
    if "model" in (args.guardian, args.rca):
        load_dotenv()
        config = load_config(args.config)
        if problems := _key_problems(config):
            print("model config problem:\n  " + "\n  ".join(problems), file=sys.stderr)
            return 1
        client = ModelClient(config, recorder=calls.append)
        models = {role: [p.model for p in rc.providers] for role, rc in config.roles.items()}

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    entries, scores = [], []
    for s in scenarios:
        bundle, score = export_scenario(s, args.guardian, args.rca, client, calls)
        (out / f"{s.id}.json").write_text(json.dumps(bundle, separators=(",", ":")))
        scores.append(score)
        entries.append({"id": s.id, "title": s.title, "family": s.family, "difficulty": s.difficulty.value,
                        "split": s.split.value, "synthetic": s.synthetic, "file": f"{s.id}.json",
                        "has_incident": bundle["incident"] is not None})

    index = {
        "version": BUNDLE_VERSION,
        "generated_at": _iso(datetime.now(timezone.utc)),
        "agents": {"guardian": args.guardian, "rca": args.rca, "models": models},
        "reportable": Split.SELFTEST not in splits,
        "scenarios": entries,
        "summary": summarize(scores),
    }
    (out / "index.json").write_text(json.dumps(index, indent=1))
    print(f"exported {len(entries)} bundles to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
