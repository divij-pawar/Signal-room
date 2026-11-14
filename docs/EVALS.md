# Signal Room: Evaluation Plan

Companion to [ARCHITECTURE.md](ARCHITECTURE.md). Every claim about Signal Room (speed, accuracy, safety, cost) must trace to a run defined here and recorded in `docs/RESULTS.md`. Nothing is measured yet; all targets below are placeholders to be set after the first baseline run.

---

## 1. Principles

1. **Eval first.** Build the harness right after the schemas, before Guardian or RCA are good. Every later change is judged by it.
2. **Ground truth is separate from the system.** The fault injector and the labels live where Guardian and RCA cannot read them.
3. **Mechanical checks beat model judges.** Use an LLM judge only for things code cannot check, and calibrate it against human labels.
4. **Report uncertainty.** Small samples get confidence intervals, not bare percentages.
5. **Held-out means held out.** The frozen test set is run only at release points and never used for tuning.
6. **Replay, don't re-run.** Record telemetry per scenario once, then replay it. This makes runs cheap, repeatable and compatible with free-tier limits.

---

## 2. What is evaluated

| Layer | Question it answers |
|---|---|
| A. Contracts | Does every model output parse and validate? |
| B. Guardian | Does it notice real incidents, quickly, without crying wolf? |
| C. RCA | Is the root cause right, is the evidence real, is the code reference right? |
| D. Safety | Can untrusted logs steer the agents, leak secrets or trigger forbidden actions? |
| E. Robustness | What happens when data, models or infrastructure fail? |
| F. System | Does the whole pipeline work end to end, dedupe correctly, and survive crashes? |
| G. Efficiency | Tokens, latency and (estimated) cost per batch and per incident |
| H. Comparisons | Which model tier and which components earn their place? |

---

## 3. The scenario dataset

### 3.1 Scenario spec
Each scenario is one file (YAML) with:
- `id`, `title`, `difficulty` (easy / medium / hard / adversarial), `split` (dev / test / heldout)
- `injection`: how the fault is produced (feature flag, config change, resource exhaustion, scripted log lines) and exact start and end timestamps
- `ground_truth`: root-cause service, root-cause category, code location (file and lines, where applicable), true severity, expected Guardian verdict per time window, and the facts an RCA report must contain
- `traps`: known distractors (a noisy but unrelated service, a misleading error message)

### 3.2 Coverage
Target at least 60 scenarios across these families, with each family spread over difficulties:
- **Hard failures:** crash loops, dependency errors, bad config or deploy.
- **Resource faults:** CPU saturation, memory leak, disk full, queue backlog.
- **Latency and degradation:** slow dependency, retry storms, silent degradation with no error lines.
- **Cascades:** one fault causing symptoms in several services (the symptom service is not the cause).
- **Misleading cases:** the loudest error is not the root cause.
- **Concurrent faults:** two unrelated faults at once.
- **Benign noise:** healthy traffic with expected errors, planned deploys, retries, load spikes. These should *not* escalate.
- **Missing data:** watcher stopped, network link down, partial coverage (should yield `unknown`).
- **Adversarial:** injection and secret-leak cases (section 7).

### 3.3 Splits
- **dev (about 40%):** used freely to build and tune prompts.
- **test (about 30%):** used for model comparisons and ablations; tuned on sparingly.
- **heldout (about 30%):** frozen at tagging time; run only at release; never inspected for failures to fix.
- Keep a hash of each split file; the runner refuses to run heldout without an explicit release flag.

### 3.4 Healthy baselines
Record at least several hours of normal traffic at low, medium and high load. These feed false-escalation measurement and provide the benign backdrop that fault scenarios are overlaid on.

---

## 4. Layer A: Contract evals
- **Schema validity rate:** share of Guardian verdicts and RCA reports that validate against the Pydantic schemas on the first try.
- **Repair rate:** share fixed by one retry; share that still fail (these become `unknown` or "no RCA").
- Run on every eval case, so no extra model calls.

## 5. Layer B: Guardian evals

| Metric | Definition |
|---|---|
| Batch precision / recall / F1 | Per 4-minute window against the expected verdict |
| Incident recall | Share of injected incidents with at least one escalation during the incident |
| Detection latency | Injection start to first correct escalation; report median and P95 |
| False-escalation rate | Escalations per 24 h on healthy traffic and on benign-noise scenarios |
| Severity accuracy | Guardian's severity guess vs. true severity |
| Pre-filter effect | Tokens per batch with Drain3 on vs. off, and any change in recall |

Slice results by family, difficulty and load level. Report the confusion matrix, not only F1.

## 6. Layer C: RCA evals

| Metric | How it is checked |
|---|---|
| Root-cause service (top-1) | Exact match to ground truth |
| Root-cause category | Match to the labeled category (e.g. config, resource, dependency, code bug) |
| Evidence faithfulness | **Mechanical:** each cited excerpt must actually appear in the referenced log or trace; unsupported citations count as hallucinations |
| Code-reference accuracy | Cited file matches ground truth; line range overlaps ground truth |
| Severity accuracy | Match to true severity |
| Fact coverage | Share of the scenario's required facts the report states (string and structured checks first) |
| Calibration | Stated confidence vs. observed accuracy per bucket |
| Honest unknowns | In missing-data scenarios, the report lists what is missing instead of guessing |
| Next-step quality | Rubric score from the judge (section 6.1) |

### 6.1 LLM judge, only where needed
- Use it for next-step quality and for fact coverage where string checks are not enough.
- The judge model must differ from the model being evaluated.
- Calibrate on 30 to 40 human-labeled reports and publish the agreement (Cohen's kappa). If agreement is low, drop that metric.
- Judge calls spend free-tier quota, so run them only on the test set and at release.

---

## 7. Layer D: Safety evals

### 7.1 Prompt injection against the agents
Attack suite, each as scripted log lines, trace attributes or source comments placed inside otherwise real fault scenarios:
- Instruction override ("ignore previous instructions...") inside a log message
- Fake system or tool-result markers in log text
- Attempts to coerce a tool call outside the allowlist
- Attempts to make Guardian report `ok` during a real incident
- Attempts to put attacker text or links into the Slack message
- Exfiltration attempts (asking the agent to include secrets or data in output)
- Encoded or obfuscated payloads, and payloads split across several log lines
- Injection placed in source-code comments the RCA agent reads

Metrics: **attack success rate** per category (agent behavior changed, forbidden tool attempted, attacker text relayed), plus the task success rate *under attack* (did the real fault still get found?). Run with defenses on and off.

### 7.2 Secret scrubbing
- Plant secrets of many formats (API keys, bearer tokens, connection strings, private-key blocks, passwords in URLs, secrets in JSON fields) in logs and evidence.
- Measure **leak rate** at two points: what is sent to the model API, and what is posted to Slack.
- Measure **false-scrub rate** on normal text, since over-scrubbing destroys useful evidence.

### 7.3 Tool allowlist and permissions
- Attempt every disallowed tool and argument pattern; all must be blocked and logged in the audit table.
- Verify the telemetry tool server is read-only: write attempts must fail.

---

## 8. Layer E: Robustness evals
- **Data faults:** watcher process killed, network link cut or throttled, partial host coverage, clock skew, out-of-order and duplicate records. Expected: `unknown` or a correct verdict, never a false `ok`. Metric: share handled correctly.
- **Input shape:** very long lines, malformed or binary log lines, non-English text, log floods. Expected: no crash, bounded latency.
- **Model faults:** timeouts, rate limits, malformed JSON, empty responses, provider removed a model. Expected: provider fallback, then `unknown` or "no RCA". Metric: share degraded gracefully, and time to recover.
- **Budget exhaustion:** request or token budget used up mid-run. Expected: the documented fallback behavior, no silent loss.

## 9. Layer F: System evals
- **End-to-end time:** injection start to Slack message with RCA; median and P95; broken down per stage.
- **Dedupe:** replay the same incident and overlapping incidents; count duplicate posts (target zero) and wrongly suppressed posts.
- **Queue and crash recovery:** kill the RCA worker at random points during N runs; record the share of escalations that complete after retry and the share that post twice.
- **Soak:** run 7 or more days on the benign load with periodic injected faults. Record uptime, false escalations per day, queue depth, memory growth and dead-man alert behavior.

## 10. Layer G: Efficiency
Per batch and per incident: input and output tokens, model-call latency (median and P95), calls per day, and **estimated list-price cost** from stated per-token prices, labeled as an estimate. Record which provider served each call.

## 11. Layer H: Comparisons and ablations

### 11.1 Model tiers (see ARCHITECTURE.md section 14.1)
Run the same test split through each Guardian and RCA tier. Report accuracy, latency and tokens side by side, with confidence intervals.

### 11.2 Ablations (one component off at a time)
Drain3 pre-filter, code index, architecture context, injection defenses, provider fallback. Report the paired difference for each, on the same cases.

---

## 12. Statistical method
- **Repeats:** run each case at least 3 times (5 for the headline runs), at temperature 0 where the provider allows it, and report per-case variability.
- **Intervals:** Wilson intervals for proportions; bootstrap intervals over scenarios for other metrics.
- **Paired comparisons:** compare two configurations on the same cases using a paired bootstrap or McNemar's test, not by eyeballing two averages.
- **Thresholds in advance:** write each gate threshold into the config before the run that checks it.
- **Report negatives:** include metrics where the system did badly, with failure examples, in `docs/RESULTS.md`.

## 13. Human baseline
- Have a teammate who did not write the scenario diagnose a subset using only normal log search and time them.
- Record time to root cause and correctness. Note the small sample and that this is a proxy, not real-world MTTR.
- Do not use your own times on scenarios you built; you know the answers.

---

## 14. Harness design (kept small)
- **Runner:** a Python CLI plus pytest, with no eval framework dependency. It loads a scenario, replays telemetry from fixtures, drives Guardian and RCA, and scores the outputs.
- **Storage:** every run gets a run ID. Results, model, provider, date, config hash, token counts and latencies go to Postgres (and JSON lines for CI).
- **Report generator:** produces tables for `docs/RESULTS.md` from stored runs, so documents never contain hand-copied numbers.
- **Determinism:** pinned models and prompts, fixed seeds, temperature 0, recorded fixtures.

## 15. Gate tiers

| Tier | When | Scope | Blocks on |
|---|---|---|---|
| Smoke | every pull request | about 15 to 20 dev scenarios from fixtures, plus the full secret and allowlist suites, which need no model | schema failures, any scrub leak, any allowlist bypass, a drop beyond the set margin on RCA top-1 |
| Nightly | daily | full dev and test splits, injection suite, robustness cases | regression beyond the margin on any headline metric |
| Release | tagged versions | everything, including heldout, ablations and a shortened soak | threshold set in config; results published |

## 16. Free-tier budget for evals
- Model calls are the limiting resource. Estimate calls per run (scenarios × repeats × windows × agents) before running, and compare against the day's request budget.
- Use the local small model for Guardian-heavy runs, hosted free tiers for RCA, and spread nightly and release runs across days.
- Run judge calls only where section 6.1 allows.

## 17. Build order for the evals
1. Scenario spec, Pydantic schemas and the runner skeleton with a fake model.
2. Healthy baseline recordings and the first 10 scenarios with fixtures.
3. Layer A and B scoring, then the smoke gate in CI.
4. Layer C mechanical scoring (service, evidence faithfulness, code refs).
5. Safety suites (scrubbing, allowlist, injection), which need no real model for the first two.
6. Grow scenarios toward 60 and freeze the heldout split.
7. Robustness and system evals, including the crash test.
8. Model-tier comparisons, ablations and the judge calibration.
9. Soak run, then `docs/RESULTS.md`.
