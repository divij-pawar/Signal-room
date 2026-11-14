# Signal Room: UI Plan

Companion to [ARCHITECTURE.md](ARCHITECTURE.md) and [EVALS.md](EVALS.md). Design only; nothing is built yet.

## 1. Goals

1. **Show the whole logic in under two minutes** to someone landing on the GitHub repo: logs in, Guardian triage, escalation, root cause with evidence, Slack alert, and the guardrails that kept it safe.
2. **Work with no backend**, so the repo can host a live demo for free (GitHub Pages) by replaying recorded runs.
3. **Be the operator console for the real system**, not a separate toy: the same views run against the live API in a local deployment.
4. **Never fake anything.** Recorded replays are labeled as recordings. The UI shows `unknown` as its own state, never as healthy.

Non-goals: user management, multi-tenant access control, editing configuration from the UI, mobile-first design (it should still work on a narrow screen).

---

## 2. Stack

| Layer | Choice | Why |
|---|---|---|
| UI | Vite, React, TypeScript | A static single-page app; no server rendering needed; builds to files GitHub Pages can host |
| Components | **shadcn/ui** (Radix primitives and Tailwind CSS) | Requested; accessible, themeable, components live in the repo |
| Data tables | TanStack Table (the shadcn DataTable pattern) | Sorting, filtering and pagination for incidents and eval results |
| Charts | shadcn Chart (Recharts) | Matches the component set; covers timelines, bars and the confusion matrix |
| Server state | TanStack Query | Caching and polling for the live API |
| Routing | React Router | Simple; enough for about seven pages |
| API | FastAPI (Python), same repo | Matches the Python stack; generates an OpenAPI spec from the Pydantic schemas |
| Types | OpenAPI spec to TypeScript types | One source of truth for the schemas in ARCHITECTURE.md section 4 |
| Live updates | Server-sent events | One-way event stream is all the UI needs |

Everything here is free. Skip anything beyond this list unless a screen needs it.

---

## 3. Two modes, one UI

| | **Replay mode** (default on GitHub Pages) | **Live mode** (local `docker compose --profile ui`) |
|---|---|---|
| Data source | Recorded event bundles in `demo-data/` loaded as static files | FastAPI over Postgres, plus an SSE stream |
| Interaction | Pick a scenario, play, pause, scrub, change speed | Real watchers, Guardian and RCA running |
| Banner | Always visible: "Recorded replay, not live data" | Shows provider, model and budget status |
| Cost | Zero | Free-tier model quota applies |

The recorded bundles are produced by the **eval harness** (EVALS.md): a bundle is a scenario's telemetry fixture plus the recorded Guardian verdicts, escalations, RCA reports, Slack messages, audit entries and ground truth. So the demo is real output of the real pipeline, replayed on a clock, and the UI and the evals share one data format.

A mode switch in the header toggles between them when a backend is reachable.

---

## 4. Pages

### 4.1 Overview (landing page)
Tells the story at a glance.
- **Pipeline strip:** Watchers → Telemetry → Guardian → Queue → RCA → Slack, as connected nodes. Each node shows status and a live counter (logs received, batches scanned, escalations, reports, posts). Clicking a node opens its page or a detail sheet.
- **Guardian timeline:** a row of 4-minute windows colored ok, escalate or unknown, with the current window highlighted.
- **Health cards:** watchers reporting vs. expected, last heartbeat, model provider status, budget remaining.
- **Latest incident card** with a one-line root cause and a link.
- A **"Take the tour"** button starting a five-step guided walkthrough (section 6).

### 4.2 Incidents and incident detail
- **List:** a data table of incidents with severity, services, status, time to root cause, confidence, and a filter bar. Command menu (⌘K) to jump to an incident.
- **Detail:** opens as a page (and as a side sheet from the Overview). Sections as tabs:
  - **Timeline:** onset, first Guardian escalation, queue claim, RCA start and finish, Slack post, with durations. Detection latency and time to root cause are shown as headline numbers.
  - **Guardian verdict:** the window, the reason, the services and traces involved, and which Drain3 templates were clustered (with before/after token counts).
  - **Root cause report:** root cause, confidence, affected services, next steps, and an **Unknowns** block when data was missing.
  - **Evidence:** each cited excerpt in an expandable row next to the real log line it came from, with a check mark that it was *verified to exist* (the faithfulness check from EVALS.md) or a warning when it could not be matched.
  - **Code:** the referenced file and lines in a read-only viewer, with the cited range highlighted.
  - **Slack preview:** the exact scrubbed message that was or would be posted, and the dedupe key (trace ID).
  - **Audit:** every model tool call, in order, with arguments, result summary, tokens and latency.
- **Answer key (replay mode and eval runs):** a toggle that reveals the ground truth after the RCA report is shown, with a correct/incorrect badge per field. Hidden by default so a viewer can judge first.

### 4.3 Coverage and health
- A grid of hosts and services with heartbeat age and state. A silent watcher turns the cell into an `unknown` state, with an explanation: "no data is not the same as healthy".
- Dead-man status for Signal Room itself, and the queue depth and age of the oldest unclaimed escalation.

### 4.4 Guardrails
Makes the security design visible.
- **Injection watch:** log lines flagged as containing instruction-like text, shown as inert quoted data with a label "treated as data, never as instructions", and what the agents did with them (nothing).
- **Scrubbing:** counts of secrets redacted before model calls and before Slack, with pattern types (not the values).
- **Allowlist:** blocked tool calls with the attempted tool and arguments.
- **Provider chain:** which free provider served each call, fallbacks taken, and budget used.

### 4.5 Scenario lab (replay mode centerpiece)
- Scenario picker grouped by family and difficulty, including benign-noise, missing-data and injection scenarios.
- Player controls: play, pause, step to next event, speed (1x to 60x), and a scrubber.
- Split view: left, the raw log stream scrolling (rendered as plain text); right, what Guardian and RCA do in response, appearing in step with the clock.
- Finishes on the incident detail with the answer key available.

### 4.6 Evals dashboard
- **Run list:** run ID, date, model tiers, split (heldout runs carry a lock badge), pass or fail against gates.
- **Headline cards:** RCA top-1 accuracy, incident recall, false escalations per day, injection attack success rate, secret leak rate, median and P95 time to root cause, tokens per incident, each with its confidence interval.
- **Charts:** Guardian confusion matrix, accuracy by difficulty and family, model-tier comparison (accuracy vs. tokens), ablation bars (paired differences), latency distribution.
- **Scenario table:** per-scenario results with filters; clicking a row opens that scenario's replay and report.
- **Compare runs:** pick two runs and see metric deltas.
- A static export of the latest published results is bundled for Pages.

### 4.7 About / Architecture
A short page with the architecture diagram, the claims policy ("every number links to a recorded run"), and links to the docs and repo.

---

## 5. Wireframes

**Overview**
```
┌ Signal Room ─────────────────── [Replay ▾] [Tour] [☾] ┐
│ ▣ Recorded replay, not live data                      │
├───────────────────────────────────────────────────────┤
│ [Watchers]→[Telemetry]→[Guardian]→[Queue]→[RCA]→[Slack]│
│   3/3 ok     1.2k logs   14 batches  0 wait   1 report │
├───────────────────────────────────────────────────────┤
│ Guardian windows  ■■■■■■□■■■■▲■■ (ok / unknown / esc.)│
├───────────────┬───────────────┬───────────────────────┤
│ Coverage 3/3  │ Budget 62%    │ Latest incident       │
│ Providers ok  │ Groq → AI St. │ Sev2 · payment cfg …  │
└───────────────┴───────────────┴───────────────────────┘
```

**Incident detail**
```
┌ Incident #12 · Sev2 · confidence: high ───────────────┐
│ Detected in 3m 40s · Root cause in 6m 05s             │
├ Timeline ─ Verdict ─ Report ─ Evidence ─ Code ─ Slack ─ Audit ┤
│ Root cause: payment service loaded a bad config …     │
│ Evidence  ✓ verified   ✓ verified   ⚠ not found       │
│ Code      payment/config.py:41-58 (highlighted)       │
│ Unknowns: backend host heartbeat missing 2 windows    │
│                                   [Reveal answer key] │
└───────────────────────────────────────────────────────┘
```

---

## 6. Guided tour
Five steps, each highlighting one element with a short popover:
1. "Logs stream in from watchers": the pipeline strip.
2. "Guardian scans 4-minute batches": the timeline.
3. "An escalation becomes a queued job": the queue node.
4. "RCA cites real evidence": an evidence row with its verified check.
5. "Guardrails treat telemetry as data": the injection watch.

Implement it with a small stepper and the shadcn Popover; no tour library.

---

## 7. shadcn/ui component map

| Need | Component |
|---|---|
| App shell, navigation | Sidebar, Breadcrumb, Separator |
| Pipeline nodes, health cards, headline metrics | Card, Badge, Progress, Tooltip, HoverCard |
| Incident and result tables | Table with TanStack Table, Input, DropdownMenu, Pagination |
| Incident detail | Tabs, Sheet (drawer from the Overview), Accordion or Collapsible (evidence) |
| Charts | Chart (Recharts) |
| Search and jump | Command (⌘K) |
| Replay controls | Button, Slider, ToggleGroup, Select |
| Mode and answer-key toggles | Switch |
| Warnings and banners | Alert |
| Loading states | Skeleton |
| Raw log and code panes | ScrollArea, Resizable |
| Confirmations and tour | Dialog, Popover |
| Notifications | Sonner |
| Theme | dark and light via the theme toggle |

---

## 8. UX rules
- **Plain language first:** labels say "Root cause" and "No data (unknown)", with terms like OTLP only in tooltips.
- **State is never color-only:** every status has an icon and text, and the palette passes contrast checks in light and dark.
- **Untrusted text is inert:** logs, evidence and Slack previews render as escaped plain text, never as HTML or Markdown, and the app ships with a strict Content Security Policy. The UI must not become the injection vector the guardrails defend against.
- **Honest empties:** when data is missing or a run has not happened, say so; do not render placeholder numbers.
- **Keyboard and screen reader support:** inherit Radix accessibility; test the main flow with the keyboard.
- **Fast first paint:** the Pages build loads one small bundle and fetches replay files on demand.

---

## 9. API surface (live mode)
Generated from the Pydantic schemas by FastAPI. Read-only; the UI cannot change system behavior.

| Endpoint | Purpose |
|---|---|
| `GET /api/pipeline` | Node status and counters |
| `GET /api/windows` | Guardian verdicts by window |
| `GET /api/incidents`, `GET /api/incidents/{id}` | List and detail, including report, evidence, audit |
| `GET /api/coverage` | Host and service heartbeats |
| `GET /api/guardrails` | Injection flags, scrub counts, blocked calls, provider chain |
| `GET /api/evals/runs`, `GET /api/evals/runs/{id}` | Eval runs and per-scenario results |
| `GET /api/stream` | Server-sent events for new windows, incidents and status changes |

Replay mode serves the same shapes from static files (`demo-data/<scenario>/*.json`), so the UI code has one data layer with two adapters.

---

## 10. Repo layout additions
```
Signal-Room/
├── api/            # FastAPI read-only API and SSE stream
├── ui/             # Vite + React + shadcn app
├── demo-data/      # recorded replay bundles exported by the eval harness
└── .github/workflows/pages.yml   # builds ui/ in replay mode and publishes to GitHub Pages
```

## 11. Showcasing on GitHub
- **README top section:** one screenshot or short GIF of the Scenario lab, a "Live demo" link to the Pages site, and a one-paragraph description with the headline measured numbers (only once real).
- **Reproducible screenshots:** a script drives the Pages build with Playwright to capture the images, so they stay current.
- **Demo-mode link in each section of RESULTS.md**, deep-linking to the matching run or scenario.
- GitHub Pages is free for public repositories; confirm the current limits.

## 12. Build order (keeps scope bounded)
The three screens that carry the showcase are **Incident detail, Scenario lab and Evals dashboard**. Build these first; the rest are cheap additions.

1. Data layer with the two adapters, and the OpenAPI to TypeScript type generation.
2. App shell (Sidebar, theme, mode banner) and the Incident detail page against a hand-made bundle.
3. Replay export from the eval harness; Scenario lab player.
4. Overview with the pipeline strip and Guardian timeline.
5. Evals dashboard from stored runs.
6. Coverage and Guardrails pages.
7. Guided tour, Pages workflow, Playwright screenshots, README.
8. Live mode: FastAPI endpoints and SSE.

The UI depends on the harness and on recorded runs, so it comes after EVALS.md steps 1 to 4. Do not let UI work delay the eval harness.
