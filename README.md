# Signal Room

*Alert to root cause, fast.* A two-tier LLM incident-response agent: a small model triages
telemetry in 4-minute batches, and a stronger model performs root cause analysis on each
escalation, posting the result to Slack. Telemetry is treated as data, never as instructions.

Design docs: [architecture](docs/ARCHITECTURE.md) · [evaluation plan](docs/EVALS.md) · [UI plan](docs/UI.md)

## Status

Milestone 1: foundations and eval harness.

| Part | State |
|---|---|
| Data contracts (Pydantic) | done: `signalroom/common/schemas.py` |
| Secret scrubber | done: `signalroom/common/scrub.py` |
| Model provider client (OpenRouter, fallback chain, budget, retries) | done: `signalroom/common/llm.py` |
| Postgres schema (verdicts, queue, reports, dedupe, audit, cost log, evals) | written: `store/schema.sql` |
| Eval harness (scenario spec, replay runner, mechanical scoring, Wilson intervals) | done: `signalroom/evals/` |
| Rule-based Guardian and naive RCA baselines | done: the numbers model-backed agents must beat |
| Drain3 window digest with cheap anomaly gating | done: `signalroom/guardian/digest.py` |
| Model-backed Guardian (Qwen3 8B via OpenRouter) | done, tested against a scripted fake model only: `signalroom/guardian/model_guardian.py` |
| Model-backed RCA agent with allowlisted read-only tools, audit trail, evidence verifier | done, tested against a scripted fake model only: `signalroom/rca/model_rca.py` |
| Telemetry pipeline (OTel Demo, Maple), notifier, queue workers, UI | not started |

Running the model agents needs `config/models.yaml` and the API key in the environment or in a
git-ignored `.env` file (`OPENROUTER_API_KEY=...`). The config names the variable in
`api_key_env`; it never holds the key itself.

```bash
.venv/bin/python -m signalroom.evals.runner --split selftest --guardian model --rca model --max-usd 0.25
```

No reported results exist yet. The only scenarios are five synthetic self-tests (split
`selftest`) that check the harness itself; they are never counted in results.

## Quickstart

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
.venv/bin/python -m signalroom.evals.runner --split selftest
```

To regenerate the self-test fixtures: `.venv/bin/python scripts/make_selftest_fixtures.py`.

Model configuration: copy `config/models.example.yaml` to `config/models.yaml` and export
`OPENROUTER_API_KEY`. Set a credit limit on the key.

Postgres (milestone 1 only runs Postgres):

```bash
POSTGRES_PASSWORD=change-me docker compose -f deploy/docker-compose.yml up -d
```

## Layout

```
signalroom/common/    schemas, scrubber, provider client, telemetry interface, agent protocols
signalroom/guardian/  Guardian agents (rule-based baseline so far)
signalroom/rca/       RCA agents (naive baseline so far)
signalroom/evals/     scenario spec, runner, scoring, statistics
evals/scenarios/      scenario specs with ground truth (agents never read these)
evals/fixtures/       recorded telemetry per scenario (JSON lines)
store/schema.sql      Postgres schema
deploy/               Docker Compose
scripts/              fixture generation
tests/                unit and harness tests
```
