// Shapes of the replay bundles written by `python -m signalroom.evals.export`.

export type VerdictKind = "ok" | "escalate" | "unknown"

export interface Proportion {
  k: number
  n: number
  p: number | null
  ci95: [number | null, number | null]
}

export interface Summary {
  scenario_runs: number
  model_calls: number
  failed_model_calls?: number
  tokens_in: number
  tokens_out: number
  cost_usd_estimate: number
  tokens_per_incident_mean: number | null
  guardian_windows_without_model_call: Proportion
  rca_blocked_tool_calls: number
  raw_evidence_faithfulness: Proportion
  window_accuracy: Proportion
  incident_recall: Proportion
  detection_latency_median_s: number | null
  false_escalation_rate: Proportion
  missing_data_reported_ok: Proportion
  rca_service_top1: Proportion
  rca_category: Proportion
  rca_severity: Proportion
  evidence_faithfulness: Proportion
  code_ref_accuracy: Proportion
  fact_coverage: Proportion
  no_rca: number
  schema_failures: number
  secret_leaks: number
  confusion: Record<string, number>
}

export interface IndexEntry {
  id: string
  title: string
  family: string
  difficulty: string
  split: string
  synthetic: boolean
  file: string
  has_incident: boolean
}

export interface Index {
  version: number
  generated_at: string
  reportable: boolean
  agents: { guardian: string; rca: string; models: Record<string, string[]> }
  scenarios: IndexEntry[]
  summary: Summary
}

export interface LogLine {
  ref: string
  t: string
  host: string
  service: string
  level: "ERROR" | "WARN" | "INFO"
  body: string
  trace_id: string | null
  redacted: boolean
}

export interface WindowVerdict {
  start: string
  end: string
  verdict: VerdictKind
  severity_guess: string
  services: string[]
  trace_ids: string[]
  reason: string
  hosts_expected: number
  hosts_reporting: number
  model_called: boolean
  gold: VerdictKind
  correct: boolean
}

export interface Evidence {
  ref: string
  excerpt: string
}

export interface CodeRef {
  file: string
  start_line: number
  end_line: number
}

export interface Report {
  trace_ids: string[]
  severity: string
  root_cause_service: string
  root_cause_category: string
  root_cause: string
  confidence: string
  evidence: Evidence[]
  code_refs: CodeRef[]
  affected_services: string[]
  next_steps: string[]
  unknowns: string[]
}

export interface AuditEntry {
  tool: string
  arguments: Record<string, unknown>
  allowed: boolean
  result_summary: string
}

export interface Incident {
  escalation: {
    window_start: string
    window_end: string
    services: string[]
    trace_ids: string[]
    severity_guess: string
    reason: string
    dedupe_key: string
  }
  report: Report | null
  no_rca_reason: string | null
  rca_latency_s: number | null
  slack: null | { posted: boolean; text: string; message: Record<string, unknown> }
  audit: AuditEntry[]
}

export interface ModelCall {
  role: string
  provider: string
  model: string
  t: string
  ok: boolean
  status: number | null
  error: string | null
  tokens_in: number
  tokens_out: number
  latency_s: number
  cost_usd: number
  redactions: number
}

export interface RCAScore {
  service_correct: boolean
  category_correct: boolean
  severity_correct: boolean
  evidence_total: number
  evidence_verified: number
  code_ref_correct: boolean | null
  facts_required: number
  facts_found: number
  hallucinated_evidence: number
}

export interface Bundle {
  version: number
  scenario: {
    id: string
    title: string
    family: string
    difficulty: string
    split: string
    synthetic: boolean
    hosts: string[]
    start: string
    windows: number
    injection: null | { start: string; end: string; method: string; description: string }
    gaps: { host: string; start: string; end: string }[]
    traps: string[]
  }
  ground_truth: {
    root_cause_service: string | null
    root_cause_category: string | null
    severity: string
    code_ref: CodeRef | null
    required_facts: string[]
    planted_secrets: number
  }
  logs: LogLine[]
  windows: WindowVerdict[]
  incident: Incident | null
  calls: ModelCall[]
  guardrails: {
    redactions: Record<string, number>
    instruction_like_refs: string[]
    blocked_tool_calls: AuditEntry[]
    redactions_before_model: number
  }
  score: {
    scenario_id: string
    incident_detected: boolean | null
    detection_latency_s: number | null
    rca: RCAScore | null
    no_rca_reason: string | null
    schema_failures: number
    secret_leaks: number
    model_calls: number
    tokens_in: number
    tokens_out: number
    cost_usd: number
  }
}
