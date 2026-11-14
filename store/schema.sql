-- Signal Room Postgres schema (ARCHITECTURE.md sections 12 and 12.2).
-- One store for verdicts, the escalation queue, RCA reports, Slack dedupe,
-- the tool-call audit log, the model-call cost log, and eval results.

CREATE TABLE IF NOT EXISTS guardian_verdicts (
    id              BIGSERIAL PRIMARY KEY,
    window_start    TIMESTAMPTZ NOT NULL,
    window_end      TIMESTAMPTZ NOT NULL,
    verdict         TEXT NOT NULL CHECK (verdict IN ('ok', 'escalate', 'unknown')),
    severity_guess  TEXT NOT NULL CHECK (severity_guess IN ('sev1', 'sev2', 'sev3', 'none')),
    payload         JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (window_start, window_end)
);

-- Durable queue between Guardian and RCA. Workers claim with FOR UPDATE SKIP LOCKED;
-- a crashed worker's lease expires and the row becomes claimable again.
CREATE TABLE IF NOT EXISTS escalations (
    id              BIGSERIAL PRIMARY KEY,
    verdict_id      BIGINT NOT NULL REFERENCES guardian_verdicts (id),
    dedupe_key      TEXT NOT NULL,
    payload         JSONB NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'claimed', 'done', 'failed')),
    attempts        INT NOT NULL DEFAULT 0,
    max_attempts    INT NOT NULL DEFAULT 3,
    lease_until     TIMESTAMPTZ,
    claimed_by      TEXT,
    last_error      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS escalations_claimable
    ON escalations (created_at) WHERE status IN ('pending', 'claimed');
-- Only one open escalation per dedupe key; retries reuse the row.
CREATE UNIQUE INDEX IF NOT EXISTS escalations_open_dedupe
    ON escalations (dedupe_key) WHERE status IN ('pending', 'claimed');

CREATE TABLE IF NOT EXISTS rca_reports (
    id              BIGSERIAL PRIMARY KEY,
    escalation_id   BIGINT NOT NULL UNIQUE REFERENCES escalations (id),
    payload         JSONB,          -- NULL when RCA was skipped ("no RCA")
    no_rca_reason   TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((payload IS NULL) <> (no_rca_reason IS NULL))
);

-- Slack dedupe: one post per dedupe key; later escalations update the thread.
CREATE TABLE IF NOT EXISTS slack_posts (
    dedupe_key      TEXT PRIMARY KEY,
    escalation_id   BIGINT NOT NULL REFERENCES escalations (id),
    message         JSONB NOT NULL,
    slack_ts        TEXT,
    post_count      INT NOT NULL DEFAULT 1,
    first_posted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_posted_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Every tool call an agent attempted, allowed or blocked.
CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL PRIMARY KEY,
    agent           TEXT NOT NULL CHECK (agent IN ('guardian', 'rca')),
    escalation_id   BIGINT REFERENCES escalations (id),
    tool            TEXT NOT NULL,
    arguments       JSONB NOT NULL,
    allowed         BOOLEAN NOT NULL,
    result_summary  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per model-call attempt; source for cost, latency and budget metrics.
CREATE TABLE IF NOT EXISTS model_calls (
    id              BIGSERIAL PRIMARY KEY,
    role            TEXT NOT NULL,
    provider        TEXT NOT NULL,
    model           TEXT NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL,
    latency_s       DOUBLE PRECISION NOT NULL,
    ok              BOOLEAN NOT NULL,
    status          INT,
    error           TEXT,
    tokens_in       INT NOT NULL DEFAULT 0,
    tokens_out      INT NOT NULL DEFAULT 0,
    cost_usd        NUMERIC(12, 6) NOT NULL DEFAULT 0,
    redactions      INT NOT NULL DEFAULT 0,
    eval_run_id     TEXT
);
CREATE INDEX IF NOT EXISTS model_calls_day ON model_calls (started_at);

CREATE TABLE IF NOT EXISTS eval_runs (
    run_id          TEXT PRIMARY KEY,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    splits          TEXT[] NOT NULL,
    config_hash     TEXT NOT NULL,
    agents          JSONB NOT NULL,    -- which Guardian and RCA implementations and models
    summary         JSONB
);

CREATE TABLE IF NOT EXISTS eval_results (
    run_id          TEXT NOT NULL REFERENCES eval_runs (run_id),
    scenario_id     TEXT NOT NULL,
    repeat          INT NOT NULL,
    scores          JSONB NOT NULL,
    PRIMARY KEY (run_id, scenario_id, repeat)
);
