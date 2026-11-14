# Signal Room: Architecture

*Alert to root cause, fast.*

Born at the Dell × NVIDIA AI Hackathon · Boston · Oct 3 2026. Now being built into a production system.
Authors: Divij Pawar, Advait Wakulkar, Derek King

> Status: design draft for the post-hackathon production build. No code yet. Items marked **(TBD)** are open questions, collected in section 9. Section 10 defines how impact will be measured, section 11 the two-machine target deployment, and section 12 which tools are adopted, deferred or skipped. The UI plan is in [UI.md](UI.md). The full evaluation plan is in [EVALS.md](EVALS.md), which supersedes the lighter eval notes in sections 10 to 14.

---

## 1. Overview and goals

Signal Room is an agent that watches an organization's telemetry and helps a site reliability engineer (SRE) get on top of incidents faster. It was designed for **fully local inference** (the hackathon build ran on a Dell Pro Max GB10 with Ollama and OpenClaw). The current build runs on two ordinary laptops and uses **hosted model APIs as a stand-in** behind a provider interface (section 3.6), so the same code can later run against local models by changing configuration. Logs are secret-scrubbed before any model call.

**Problem.** Downtime is expensive and slow to resolve.

| Metric | Figure | Source |
|---|---|---|
| Average cost of downtime | about $9,000 / minute | Splunk and Oxford Economics, 2024, Global 2000 average |
| Typical resolution time for a critical incident | 30 min to 2 hr | about 60% of organizations report this range |

**Goals**
- Cut the **cost per minute of downtime** by detecting problems early.
- Cut **MTTR** by handing the SRE a root cause, not just an alert.
- Keep data on-prem by design: collection, storage and orchestration are local, and the model backend is pluggable (hosted today, local-capable).

**Non-goals (v1)**
- Auto-remediation. The system reads and reports; it does not change production.
- Replacing the SRE's judgment. It produces an analysis the SRE verifies.
- Multi-channel paging or on-call rotation management.

---

## 2. System diagram

```
 MONITORED SERVICES              COLLECTOR (model backend: pluggable, hosted or local)         NOTIFY
┌──────────────┐        ┌────────────────┐    ┌──────────────┐  escalate  ┌──────────────┐    ┌─────────┐
│ Server 1     │        │ Telemetry      │    │ Guardian     │───────────▶│ RCA agent    │───▶│ Slack   │
│  Watcher svc │──OTLP─▶│ server         │───▶│ always on    │            │ on escalation│    │ one     │
├──────────────┤        │ Maple + OTel   │    │ small model  │            │ strong model │    │ channel │
│ Server 2     │──OTLP─▶│ + storage      │    │ 4-min batches│            │              │    │ Sev 1+2 │
│  Watcher svc │        │                │    │ in < 4 min   │            │              │    │ + root  │
├──────────────┤        │                │    └──────────────┘            └──────┬───────┘    │ cause   │
│ Server 3     │──OTLP─▶│                │◀──────────────────────────────────────┘            └─────────┘
│  Watcher svc │        └────────────────┘   pulls raw evidence and source code,
└──────────────┘                              with context of the whole service architecture
 always-on log stream
```

Data flow:
1. Watchers stream logs to the telemetry server over OTLP.
2. Guardian pulls live logs from the telemetry server in 4-minute batches and classifies them.
3. On anything suspicious, Guardian escalates to the RCA agent.
4. The RCA agent pulls raw evidence and source code back from the telemetry server and builds a root cause analysis.
5. For Sev 1 and Sev 2, the notifier posts the alert with the root cause to one Slack channel.

---

## 3. Components

### 3.1 Watcher service (one per server)
- Runs on each on-prem server and streams logs continuously (the "always-on log stream").
- Exports to the telemetry server over **OTLP**.
- Requirements:
  - Local buffering with bounded disk usage, so a telemetry outage does not drop logs.
  - Stamps each record with host, service and trace identifiers when available.
  - Emits a periodic heartbeat. A missing heartbeat is itself a signal (see "unknown, not healthy" in section 5).
- Implementation: Python service using the OpenTelemetry SDK. **(TBD: tail files vs. journald vs. an existing OTel collector as the watcher.)**

### 3.2 Telemetry server (Maple + OTel)
- Runs on the collector machine (laptop B) with local storage and receives OTLP from all watchers.
- Maple is the store and query layer; an OTel collector is the ingest front door.
- Deployment config (docker-compose for Maple and the collector, retention settings) lives in `deploy/`.
- Exposes a narrow read interface used by Guardian and the RCA agent: time-range log queries, trace lookup, and raw evidence fetch. **(TBD: Maple's actual query API.)**
- Retention must cover at least the longest RCA lookback. **(TBD: window and disk budget.)**

### 3.3 Guardian (always on)
- **Model:** a small, cheap model through the provider interface (section 3.6). Reference target: Qwen3 8B class; hosted open-weight Qwen is the preferred stand-in. **(TBD: provider and exact model.)**
- **Job:** every cycle, pull the last **4-minute batch** of live logs and decide whether anything needs escalation. The scan must finish in **under 4 minutes**, so scanning keeps pace with ingest and never builds a backlog.
- **Tools:** it may run only **two allowlisted collector scripts** and nothing else (no shell, no arbitrary queries).
- **Output:** a structured verdict per batch, `ok`, `escalate`, or `unknown`, with a severity guess and the trace and service identifiers involved.
- **Escalation payload** (see section 4.3) carries references to evidence, not the evidence itself, so the RCA agent fetches raw data directly.
- Pre-filtering (dedupe, rate summaries, template clustering) keeps each call small, which holds down token cost and latency and keeps the batch within the model's context. **(TBD: log-volume assumptions.)**

### 3.4 RCA agent (on escalation)
- **Model:** a stronger model through the provider interface (section 3.6), called only on escalation. Reference target: Qwen3.8-27B (the hackathon model). **(TBD: hosted provider and model; Ollama tag and quantization for a later local run.)**
- **Job:** root cause analysis of each escalation.
- **Inputs:** the escalation payload, raw evidence pulled from the telemetry server, **source code**, and **context of the whole service architecture** (service map and dependencies).
- **Output:** an RCA report (section 4.4): probable root cause, supporting evidence with citations, affected services, severity, and suggested next steps for the SRE.
- Evidence and code are read-only. The agent cannot change anything.
- **(TBD: how source code is made available: a checked-out mirror on the collector, a repo index, or per-service paths.)**

### 3.5 Slack notifier
- Posts alerts for **Sev 1 and Sev 2** only, with the root cause included.
- **One channel.**
- **De-duplicated by trace:** repeated escalations for the same trace update or are suppressed rather than re-posted.
- **Secret-scrubbed** before posting (tokens, keys, credentials, connection strings).
- **(TBD: Slack delivery mechanism: incoming webhook vs. bot token; thread-update behavior.)**

### 3.6 Model provider interface (`common/`)
- Guardian and RCA both call one function, roughly `chat(role, messages, tools) -> response`. They never import a vendor SDK directly.
- Config maps each role (`guardian`, `rca`) to `base_url`, `model`, timeout and token limits. Hosted APIs and Ollama both expose an OpenAI-compatible endpoint, so one client covers both.
- Moving to local hardware later is a config change, not a code change.
- The client enforces: a **scrub step before every outbound call**, per-call timeout and retry with backoff, a **daily spend cap**, and logging of tokens, latency and cost for every call (these feed the metrics in section 10).
- Credentials come from environment variables only and never appear in the repo or in logs.
- Fallback: if the RCA provider is down or over budget, escalate with Guardian's verdict alone, flagged "no RCA".

---

## 4. Data contracts (draft)

### 4.1 Watcher → telemetry
Standard OTLP logs. Resource attributes: `host.name`, `service.name`, plus `trace_id` / `span_id` on records where available.

### 4.2 Guardian batch verdict
```json
{
  "window": {"start": "...", "end": "..."},
  "verdict": "ok | escalate | unknown",
  "severity_guess": "sev1 | sev2 | sev3 | none",
  "services": ["..."],
  "trace_ids": ["..."],
  "reason": "short text",
  "coverage": {"hosts_expected": 3, "hosts_reporting": 3}
}
```

### 4.3 Escalation payload (Guardian → RCA)
Verdict fields above, plus evidence **references** (query handles, time ranges, trace IDs). No raw log bodies are copied into the payload.

### 4.4 RCA report
```json
{
  "trace_ids": ["..."],
  "severity": "sev1 | sev2 | sev3",
  "root_cause": "text",
  "confidence": "high | medium | low",
  "evidence": [{"ref": "...", "excerpt": "..."}],
  "code_refs": [{"file": "...", "lines": "..."}],
  "affected_services": ["..."],
  "next_steps": ["..."],
  "unknowns": ["data that was missing"]
}
```

### 4.5 Slack message
Severity, affected services, root cause, confidence, evidence links, `unknowns`, and the trace ID used for dedupe. All fields are scrubbed.

---

## 5. Guardrails and threat model

| Guardrail | Threat it addresses | Design implication |
|---|---|---|
| Guardian runs only **two allowlisted collector scripts** | Compromised or confused model running arbitrary commands | Fixed tool list; arguments validated; no shell tool |
| **Telemetry is data, never instructions** | Prompt injection through log lines (an attacker controls what gets logged) | Log content is wrapped as untrusted data in prompts; model output cannot trigger tools beyond the allowlist; injection test lines in the eval set |
| Posts go to **one channel**, **secret-scrubbed**, **de-duplicated by trace** | Data leakage, alert fatigue | Fixed destination in config; scrubber runs on the final message; trace-keyed dedupe store |
| **Missing data is reported as unknown, not healthy** | False reassurance when watchers or ingest fail | Heartbeat and coverage checks feed the verdict; `unknown` is a first-class state and is surfaced |

Additional notes:
- With hosted models, the only data leaving the network is the scrubbed digest or evidence sent to the model API. Test data is synthetic. Any move to real logs needs a review of what is sent and the provider's retention terms.
- RCA has read-only access to code and evidence.
- Model output is validated against the schemas in section 4 before it is acted on.

---

## 6. Latency and capacity budget

- Guardian cadence: 4-minute batches, each scan completing in under 4 minutes.
- Model calls go over the network, so the budget includes API latency, provider rate limits and timeouts. Record **model-call latency separately** from pipeline latency, so numbers stay comparable if the backend changes to local hardware.
- Guardian makes about 360 calls per day (one per 4-minute batch), so use a small model and short digests. RCA calls happen only on escalation. **(TBD: measure RCA time to first result and cost per RCA.)**
- If a Guardian call fails or times out, the batch is reported as `unknown`, not `ok`.
- End-to-end target: incident onset → Slack alert with root cause well under the 30-minute low end of typical resolution. **(TBD: set a concrete target, e.g. P50 and P95.)**
- Worst case detection delay is about one batch window plus the scan time, so up to roughly 8 minutes. **(TBD: whether to overlap windows.)**

---

## 7. Proposed repo layout (Python)

As built: the Python components live as subpackages of one `signalroom/` package
(`signalroom/common`, `signalroom/guardian`, `signalroom/rca`, `signalroom/evals`, and later
`signalroom/watcher` and `signalroom/notifier`), so names like `common` never collide with
other installed packages. `evals/` at the top level holds scenario data and fixtures only.
Code references in reports use `start_line`/`end_line` integers rather than a `lines` string.

```
Signal-Room/
├── docs/ARCHITECTURE.md
├── deploy/            # docker-compose + config for Maple and the OTel collector
├── watcher/           # per-server log streaming service
├── guardian/          # 4-minute batch scanner, allowlisted collectors
├── rca/               # root cause analysis agent
├── notifier/          # Slack poster: scrubber, dedupe
├── common/            # schemas, telemetry client, model provider client (hosted or Ollama)
├── api/               # read-only FastAPI service for the UI (see UI.md)
├── ui/                # Vite + React + shadcn/ui app, replay and live modes (see UI.md)
├── demo-data/         # recorded replay bundles exported by the eval harness
├── store/             # Postgres schema and queue access (dedupe, verdicts, audit log, escalation queue)
├── evals/             # fault scenarios, held-out set, prompt-injection cases, replay fixtures, CI gate runner
└── tests/             # unit tests
```

---

## 8. Milestones

1. **Telemetry path:** Maple + OTel up from `deploy/`; one watcher streaming from one real server.
2. **All watchers:** three servers streaming; heartbeat and coverage reporting.
3. **Guardian v0:** 4-minute batch pull, schema-validated verdicts, the two collector scripts.
4. **RCA v0:** evidence and code retrieval, structured report.
5. **Notifier:** Slack post, scrubber, trace dedupe.
6. **Hardening:** prompt-injection and missing-data eval cases, latency measurements against the budget.
7. **Demo run:** an injected real fault, end to end.

---

## 9. Open questions
(Item 1 is the most important: the numbers in section 10 depend on it.)

1. Production target: which real environment (company, lab or open-source stack) will Signal Room watch, and how many services and logs per day?
2. Maple's query API and the read interface Guardian and RCA will use.
3. How source code is made available to the RCA agent.
4. Severity rubric: what defines Sev 1 vs. Sev 2 vs. below.
5. Watcher implementation: tail files, journald, or an OTel collector.
6. Retention window and storage budget on the collector laptop.
7. Slack delivery mechanism (webhook vs. bot token) and thread behavior.
8. Evaluation plan: how Guardian and RCA accuracy and the latency budget are measured.
9. Whether the two allowlisted collector scripts already exist, and what they collect.
10. Provider is **OpenRouter** (decided). Open: the monthly credit limit to set on the API key, and whether to use the `:batch` route for eval runs (see section 15).
11. Ownership: which components each author owns (a likely split is Guardian, RCA, the provider interface and evals). Resume bullets cover only owned components.

---

## 10. Production hardening and measurable impact

The hackathon version proves the idea. The production build is judged on **measured numbers**, so every claim below is something we instrument and record. Do not quote a figure on a resume until a run has produced it.

### 10.1 What "production" adds
- **Reliability:** watcher disk buffering, Guardian and RCA as supervised services (systemd or containers) with health checks, and a "dead-man" alert if Signal Room itself stops (it must not fail silently).
- **Observability of the observer:** export Signal Room's own metrics (batch scan latency, escalations, RCA duration, Slack posts, dedupe hits) to Maple.
- **Security:** secrets only via environment or a secret store, TLS and auth on OTLP ingest, least-privilege read-only access to code and logs, audit log of every model tool call.
- **Operability:** versioned config, structured logs, runbook, one-command deploy from `deploy/`, and CI that runs unit and eval tests.
- **Model ops:** pinned model tags, a regression eval before any model or prompt change, and a fallback when the RCA model is unavailable or over budget (escalate with Guardian's verdict alone, flagged as "no RCA"), and a spend cap.

### 10.2 Metrics to collect
| Metric | How to measure | Why it matters |
|---|---|---|
| **Detection latency** | Time from fault injection to Guardian `escalate` | Directly cuts downtime minutes |
| **Time to root cause (MTTR proxy)** | Fault injection to Slack message with RCA, vs. a baseline SRE manually diagnosing the same fault | Headline claim against the 30 min to 2 hr norm |
| **RCA accuracy** | Fraction of injected faults where the report names the true root cause (top-1), graded against ground truth | Credibility of the number above |
| **Guardian precision / recall** | Labeled log batches: true incidents vs. noise | Alert fatigue vs. missed incidents |
| **False-escalation rate** | Escalations per day on healthy traffic | Operating cost and trust |
| **Prompt-injection resistance** | Share of crafted malicious log lines that fail to change behavior | Security claim |
| **Missing-data correctness** | Share of watcher or ingest outages reported as `unknown`, not `ok` | Safety claim |
| **Scan throughput** | Logs per batch and per day handled within the 4-minute budget | Scale claim |
| **Dedupe effectiveness** | Duplicate posts suppressed per incident | Noise reduction |
| **Cost per incident** | Tokens × price for Guardian plus RCA calls, per injected fault | Operating-cost claim |
| **Accuracy by model** | RCA accuracy and cost for a small vs. a strong model on the same held-out faults | A real finding about model choice |
| **Model-call latency** | Per-call time, reported separately from pipeline time | Portable across backends |
| **Cost avoided (estimate)** | Minutes saved × $9,000/min, with the assumption stated | Business framing; label it an estimate |

### 10.3 How to generate defensible numbers
1. **Fault-injection harness** (chaos tests in `tests/`): scripted faults such as crash loops, dependency timeouts, bad deploys, disk full, memory leak, and slow queries across the three servers, with ground-truth labels. Aim for 30+ distinct scenarios.
2. **Baseline:** time a human (or a plain log-search workflow) on the same scenarios to get a before/after.
3. **Soak test:** run for 7+ days on real traffic to measure false-escalation rate and uptime.
4. **Report** results in a `docs/RESULTS.md` with methodology, so each resume bullet traces to a recorded run.

### 10.4 Resume bullet shapes (fill in after measuring)
Write bullets only about the components you personally own (see open question 11), and only after a recorded run backs each number. Use "two-tier agent system", not "multi-agent". The tools named below are only those adopted in section 12.

- Built a two-tier LLM incident-response agent (small-model triage plus strong-model root cause analysis) over an OTLP log pipeline, cutting time to root cause from **X min to Y min** across **N** injected faults at **$C** per incident.
- Engineered a streaming scan of **N** log lines/day in 4-minute batches, using Drain3 template clustering to cut tokens per batch by **T%**, holding **P% precision / R% recall** at **F** false escalations/day.
- Hardened the agent against prompt injection from untrusted logs (allowlisted tools, data/instruction separation, secret scrubbing), blocking **X of N** adversarial cases, and reporting watcher outages as `unknown` in **X%** of outage tests.
- Automated a CI eval gate over **N** fault scenarios (one third held out) that blocks model or prompt changes on an accuracy regression, and compared small vs. strong models on cost and RCA accuracy.
- Shipped with schema-validated model output (Pydantic), Postgres-backed dedupe, audit log and durable escalation queue, health checks and a dead-man alert; **X days** of continuous soak uptime.
- Validated crash recovery by killing the RCA worker mid-incident: **X%** of escalations completed after retry.

---

## 11. Target environment and deployment topology

**Hardware:** two low-powered laptops and no GPU, so model inference uses hosted APIs. *Laptop A* is the watched machine and *laptop B* is the collector. Both are light on compute because inference is remote. If the demo app is too heavy for laptop A, run it on a small cloud VM instead; nothing else changes. If the roles are reversed, only the hostnames change.

```
 WATCHED MACHINE (laptop A)                        COLLECTOR MACHINE (laptop B)
┌─────────────────────────────────────┐          ┌───────────────────────────────────────┐
│ OpenTelemetry Demo (Astronomy Shop) │          │ OTel collector → Maple (+ storage)    │
│  services split into 3 groups       │          │ Guardian  (small hosted model)        │
│  load generator (steady traffic)    │──OTLP───▶│ RCA agent (strong hosted model)       │
│  fault injector (flags + custom)    │          │ Slack notifier                        │
│ Watcher service × 3 (one per group) │          │ Source-code mirror of the demo (RO)   │
└─────────────────────────────────────┘          └───────────────────────────────────────┘
```

### 11.1 What this changes
- The original design has three physical servers. Here, three **service groups** on one host stand in for them, each with its own watcher, container network and `host.name` label.
- Be precise on a resume: say "3 watcher agents across N services on a monitored host", not "3 servers".
- The network hop between the machines is real, so OTLP auth/TLS and the "ingest down → `unknown`" behavior can be tested for real by unplugging or throttling the link.
- Keep the fault injector on the watched machine only. Guardian and RCA must never be able to reach it, so the system cannot "see" the ground truth.
- The RCA agent reads source from a read-only mirror on the collector, not from the watched machine.

### 11.2 Suggested service groups (adjust to the demo's actual service list)
| Group | Examples | Why |
|---|---|---|
| Edge | frontend, load generator | Where user-visible errors appear |
| Core | cart, checkout, payment, product catalog | Most fault scenarios |
| Backend | recommendation, ad, Kafka/queue, database | Cross-service and resource faults |

### 11.3 Fault catalog (starter set; grow to 30+)
Labeled with the true root cause, kept in a file the agents cannot read.

| # | Scenario | Type |
|---|---|---|
| 1 | Product catalog returns errors | built-in flag |
| 2 | Payment service failure | built-in flag |
| 3 | Ad service high CPU | built-in flag |
| 4 | Kafka queue backlog | built-in flag |
| 5 | Slow image loads | built-in flag |
| 6 | Bad config pushed to one service | custom |
| 7 | Disk fills on the watched host | custom |
| 8 | Memory leak in one service | custom |
| 9 | Dependency timeout cascade | custom |
| 10 | Misleading error message (true cause elsewhere) | custom, hard |
| 11 | Log line with a prompt-injection payload during a real fault | security |
| 12 | Watcher or link outage (must report `unknown`) | safety |

Hold out at least a third as a test set that prompts are never tuned on.

### 11.4 Capacity checks to run first
- Provider rate limits and per-call latency for both roles, with token counts per Guardian batch and per RCA, to set the spend cap. Record the numbers; do not assume them.
- Memory and CPU headroom on both laptops with the demo, Maple and the collector running together.
- Log volume per minute from the demo at the chosen load level, to size Guardian's 4-minute batch and pre-filtering.
- Storage growth per day in Maple, to set retention for the 7-day soak.

---

## 12. Tooling decisions

Rule: add a tool only if it solves a problem the design already has, costs little on two low-powered laptops, and produces a number or a defended design choice. Everything else is deferred or skipped.

| Tool | Decision | Problem it solves | Cost / risk |
|---|---|---|---|
| **Pydantic** | **Adopt** | Validates every model output against the section 4 schemas before use | Near zero; a Python library |
| **Postgres** | **Adopt** | One store for trace dedupe, verdict history, the audit log of tool calls, model-call cost log, and the escalation queue | One container; replaces what would otherwise be several ad hoc stores |
| **Durable queue** (Postgres-backed, `FOR UPDATE SKIP LOCKED`) | **Adopt, on Postgres** | Guardian → RCA handoff survives an RCA crash; idempotent consumers and retries; enables the kill-test metric | Small amount of code; no Redis, so one fewer service |
| **Drain3** | **Adopt** | Log template clustering as the Guardian pre-filter, which cuts tokens per batch | Small pip dependency; before/after token count is a clean metric |
| **Source-code index: ripgrep (+ tree-sitter outlines)** | **Adopt ripgrep first** | Resolves the TBD on how RCA reads code: stack trace or log line → file and lines | Cheap; the demo repo is small. Try pgvector only if a comparison on the held-out set shows it helps |
| **CI eval gate** (GitHub Actions) | **Adopt, with care** | Blocks model or prompt changes that lower RCA accuracy or injection resistance | See notes below |
| **Typed read-only telemetry tools** | **Adopt as plain Python first** | The narrow read interface for Guardian and RCA (time-range query, trace lookup, evidence fetch), validated with Pydantic | Small. Check what Maple's query API actually offers first |
| **MCP server wrapping those tools** | **Adopt (upgraded from defer, see section 14)** | Read-only telemetry tools run in a separate process, so a prompt-injected agent cannot reach anything beyond them; this directly supports the injection-hardening claim | Extra moving part. Build the plain Python tools first, then wrap them |
| **Langfuse** | **Defer** | UI for model traces | The provider client already logs tokens, latency and cost to Postgres, which covers the cost metrics. Self-hosted Langfuse is heavy for laptops. Add it only if debugging RCA traces becomes painful |
| **Prometheus / Grafana** | **Defer, reuse if already running** | Dashboards for Signal Room's own metrics | The design already exports them to Maple through OTel. Do not build a second pipeline. The OTel demo ships Grafana, so use it for a demo view if resources allow |
| **Kubernetes, Terraform** | **Skip** | none needed | Docker Compose is enough |
| **Kafka** | **Skip (not ours)** | none | It is a monitored service inside the OTel demo, not something we build. Do not list it as a skill |

### 12.1 Notes on the CI eval gate
- Evals call a paid model and depend on live telemetry, so a naive gate is slow, flaky and costly.
- Make it **replay-based**: record telemetry snapshots for each fault scenario once, then replay them from fixtures. No watchers, load generator or Maple needed in CI.
- Run a **small subset on every pull request** and the **full set, including the held-out third, nightly or on demand**. Hold out scenarios the prompts were never tuned on.
- Set temperature to 0, run each case a few times, and gate on **thresholds** (for example, RCA accuracy not dropping more than a set margin), not exact output matches.
- Report gate runs and their cost in `docs/RESULTS.md`.

### 12.2 Notes on the queue and kill-test
- Escalations are rows in Postgres with a status, attempt count and lease. RCA workers claim rows with `SKIP LOCKED`, so a killed worker's row becomes claimable again after the lease expires.
- RCA is idempotent per trace ID, and the notifier dedupes by trace, so a retry cannot double-post.
- Kill-test: kill the RCA worker mid-incident across N runs and record the share of escalations that complete after retry.

### 12.3 Build order that respects these decisions
1. Pydantic schemas, Postgres schema and the provider client with cost logging.
2. Telemetry path and watchers (milestones 1 and 2).
3. Guardian with Drain3, writing verdicts to Postgres.
4. Queue, then RCA with the ripgrep code index.
5. Notifier with trace dedupe.
6. Fault harness, replay fixtures, then the CI eval gate.
7. Soak test and `docs/RESULTS.md`; only then fill the resume bullets.

---

## 13. $0 budget plan

Constraint: no spending. Everything below is free to run; the only limits are provider rate limits, which are small enough to design around. Free-tier limits and terms change, so confirm each one on the provider's own dashboard before relying on it.

### 13.1 Software
Postgres, Drain3, ripgrep, Pydantic, Docker Compose, the OpenTelemetry Demo and Maple are all free. CI uses GitHub Actions (free for public repos; check the limits for private ones). Nothing in section 12 needs a paid plan.

### 13.2 Models
- **Guardian:** make most batches cost zero model calls. Drain3 and simple rules (error-rate jump, new log template, heartbeat gap) decide whether a batch is boring. Only batches with an anomaly go to a model. That cuts the roughly 360 calls per day a naive loop would make. Optionally run a small quantized model locally on laptop B through Ollama, which costs nothing per call.
- **RCA:** runs only on escalation, so call volume is low. Use a free hosted tier.
- **Provider chain:** configure an ordered list of free providers per role (for example Groq, Google AI Studio, OpenRouter `:free` models, Cerebras). On a rate-limit error, the client falls through to the next provider. This extends section 3.6.
- **Budget unit:** replace the dollar cap with a **per-provider daily request and token budget**, tracked in Postgres. When the budget is spent, Guardian reports `unknown` and RCA is skipped ("no RCA"), as in section 3.6.

### 13.3 Constraints to design for
- **Prompt privacy:** some free tiers may use your prompts for training. That is acceptable here because the test data is synthetic (the OTel Demo). Do not point this setup at real company logs.
- **Rate limits:** a free hosted model may allow only tens of requests per day. Run the full eval set across several days, or in nightly batches, and replay from recorded fixtures (section 12.1) instead of calling live services.
- **Model drift:** free models get renamed, limited or removed. Pin model names in config, record the model and date with every result in `docs/RESULTS.md`, and re-run evals if you switch.
- **Reproducibility:** free hosted models may not be the same weights each day. Keep temperature at 0 and report results as measured on a given date.

### 13.4 Cost metric without spending
Record **tokens per incident** (Guardian plus RCA). Also report an **estimated list-price cost** computed from those tokens and a stated per-token price, labeled as an estimate. Do not write "$0 per incident" as an achievement. The honest framing is "tokens per incident, and estimated cost at list price".

### 13.5 Hardware
- Laptop A runs the OTel Demo, which is heavy. If it does not fit, run a reduced set of services, and report exactly which ones.
- Do not use a cloud VM unless it is free for your use. Section 11's cloud VM option is only a fallback.

---

## 14. Impact upgrades (still $0)

Principle: a project sounds impressive when interviewers can probe it and the numbers hold up. Tool count does not do that, and an unneeded tool invites the question "why is that here?". The upgrades below are the ones that make a claim stronger and cost nothing. They override section 12 where they differ.

### 14.1 Model strategy: a measured study, not a single model
Run the same held-out fault set through several tiers and report accuracy, latency and tokens for each. Check which models each free provider currently offers; do not rely on names written here.

| Role | Tiers to compare |
|---|---|
| Guardian | rules and Drain3 only (no model), a small local model through Ollama, a small hosted model |
| RCA | a mid-size hosted open-weight model, the largest open-weight model a free tier offers, and one frontier model on a free tier as a ceiling reference |

The result worth reporting is where accuracy stops improving as the model grows, and what each tier costs in tokens. That is a real engineering finding, and it makes "model-agnostic" a tested claim.

### 14.2 Ablations
Each ablation is one extra run of the eval set with one component switched off:
- Drain3 pre-filter on vs. off (accuracy, tokens per batch).
- Code index on vs. off (RCA accuracy, with and without source access).
- Architecture context on vs. off.
- Injection defenses on vs. off (injection success rate).

These show which design decisions earned their place, and they are cheap once the eval harness exists.

### 14.3 Tools promoted or added
- **MCP server for the telemetry tools:** adopted. It gives a security boundary (separate process, read-only, typed schemas), not just a protocol label.
- **OpenTelemetry GenAI semantic conventions:** emit traces for every Guardian and RCA call (model, tokens, latency, tool calls) into Maple through the OTel stack already in use. This is observability of the agents themselves, with no new service. It stands in for Langfuse, which stays deferred.
- **Open benchmark release:** publish the fault catalog, labels (except the held-out answers), replay fixtures and eval runner in the repo with a reproduction guide. A reproducible benchmark is a stronger signal than a demo video.

Still skipped: Kubernetes, Terraform, a vector database without an ablation that justifies it, and Kafka.

### 14.4 Claims policy
- Say "tested across N models and M faults", never "state of the art".
- Every number links to a run in `docs/RESULTS.md` with the model, date and provider.
- Prefer one result you can defend for 10 minutes over three you cannot.
- Name what you built: the pipeline, the harness, the guardrails. Do not list tools you only installed.

---

## 15. OpenRouter cost estimate (original model selection)

Decision: use **OpenRouter** with the original models, Qwen3 8B for Guardian and Qwen3.8-27B for RCA. This replaces the free-tier-first plan in section 13 as the default; the provider chain and spend cap still apply, and the free-tier fallbacks remain usable.

### 15.1 Prices (unverified)
Prices come from third-party trackers that disagree with each other, and the OpenRouter pages did not show them in search results. Check the live model pages before relying on these.

| Model | Input per 1M tokens | Output per 1M tokens | Notes |
|---|---|---|---|
| Qwen3 8B | about $0.117 (one tracker: $0.05) | about $0.455 (one tracker: $0.40) | Guardian |
| Qwen3.8-27B | about $0.45 (range seen: $0.21 to $0.45) | about $3.20 (range seen: $2.55 to $3.20) | RCA |
| Qwen3.8-27B `:batch` route | about $0.16 | about $2.00 | Asynchronous; suited to eval runs, not live alerts |

### 15.2 Assumptions (replace with measured values in the first week)
- Guardian call: about 3,000 input and 500 output tokens. Reasoning tokens bill as output, so keep thinking short or off for Guardian.
- RCA run: about 100,000 input tokens (the agent re-reads context across several tool turns) and 6,000 output tokens; heavy reasoning could reach 15,000 output.
- An eval run has about 10 Guardian windows and one RCA per faulty scenario.

### 15.3 Estimated cost
| Item | Estimate |
|---|---|
| One Guardian call | about $0.0004 to $0.0006 |
| One RCA run | about $0.04 to $0.06 (about $0.09 with heavy reasoning) |
| Guardian, every batch called (360 per day) | about $0.13 to $0.21 per day, $4 to $6 per month |
| Guardian, Drain3 gating at about 30% | about $2 per month |
| Smoke run on a pull request (about 18 scenarios) | about $0.60 to $1.00 |
| Full eval run (60 scenarios × 5 repeats) | about $10 to $25 |
| One ablation on the test split | about $3 to $5 (five ablations: $15 to $25) |
| 7-day soak (live) | about $2 to $4 |
| Nightly full dev and test run | about $4 to $7 per night, or $130 to $200 per month |

### 15.4 What this means
- Live operation is cheap. Evals are where the money goes.
- **Do not run the full eval nightly.** Run the smoke set on pull requests, the full set weekly or before a release, and ablations once per model change.
- Estimated total through the first published results (development runs, one full release run, ablations and a soak): roughly **$60 to $100**, or roughly **$35 to $60** if eval runs use the batch route and replay fixtures. These are estimates from assumed token counts, not measurements.

### 15.5 Controls
- Set a **credit limit on the OpenRouter API key** and add only small amounts of credit at a time (check the key settings and any fees on credit purchases).
- Keep the provider client's request and token budget in Postgres as a second cap, and stop with "unknown" or "no RCA" when it is hit.
- Reduce spend with Drain3 gating, replay fixtures, the batch route, prompt caching where the provider supports it, and a local small model for Guardian-heavy eval runs.
- Record measured tokens per call from the first runs and recompute this table.

### 15.6 Update (2026-11-13): live prices and a retired model
- **Qwen3 8B was retired on OpenRouter on 2026-10-09** (requests return 404). Guardian now uses `qwen/qwen3.5-9b`, the closest small dense Qwen model, at $0.165 input / $0.243 output per million tokens.
- **Qwen3.8-27B** lists at $0.15 input / $1.875 output per million tokens (`:batch` $0.16 / $2.00), cheaper than the tracker figures in 15.1. These come from OpenRouter's models API.
- With these prices, RCA runs cost roughly half of the 15.3 estimates. Recompute from measured tokens.
- For testing without credits, `config/models.free.yaml` uses free NVIDIA Nemotron models (no Qwen model is free). Results from it are not comparable to the Qwen configuration.
