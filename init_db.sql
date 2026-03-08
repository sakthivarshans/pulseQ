-- NeuralOps PostgreSQL schema initialization
-- Runs once on first container start via docker-entrypoint-initdb.d

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ── Incidents ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS incidents (
    incident_id        UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title              TEXT NOT NULL,
    description        TEXT,
    severity           VARCHAR(2) NOT NULL,   -- P1-P4
    status             VARCHAR(20) NOT NULL DEFAULT 'detected',
    detected_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    investigating_at   TIMESTAMPTZ,
    remediating_at     TIMESTAMPTZ,
    resolved_at        TIMESTAMPTZ,
    post_mortem_at     TIMESTAMPTZ,
    primary_service    TEXT NOT NULL,
    affected_services  JSONB NOT NULL DEFAULT '[]',
    blast_radius       JSONB,
    environment        TEXT NOT NULL DEFAULT 'production',
    cloud_provider     TEXT NOT NULL DEFAULT 'unknown',
    region             TEXT,
    correlated_anomaly_ids JSONB NOT NULL DEFAULT '[]',
    peak_anomaly_score FLOAT NOT NULL DEFAULT 0,
    ml_confidence      FLOAT NOT NULL DEFAULT 0,
    rca_id             UUID,
    action_ids         JSONB NOT NULL DEFAULT '[]',
    pagerduty_incident_id TEXT,
    slack_thread_ts    TEXT,
    jira_ticket_key    TEXT,
    mttr_minutes       FLOAT,
    is_false_positive  BOOLEAN NOT NULL DEFAULT FALSE,
    runbook_id         UUID,
    labels             JSONB NOT NULL DEFAULT '{}',
    acknowledged_by    TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_incidents_status   ON incidents(status);
CREATE INDEX idx_incidents_severity ON incidents(severity);
CREATE INDEX idx_incidents_detected ON incidents(detected_at DESC);
CREATE INDEX idx_incidents_service  ON incidents(primary_service);

-- ── RCA Results ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rca_results (
    rca_id                       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id                  UUID NOT NULL REFERENCES incidents(incident_id),
    created_at                   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    llm_provider_used            TEXT NOT NULL,
    root_cause_summary           TEXT NOT NULL,
    root_cause_confidence        FLOAT NOT NULL,
    primary_contributing_factor  TEXT NOT NULL,
    secondary_contributing_factors JSONB NOT NULL DEFAULT '[]',
    affected_components          JSONB NOT NULL DEFAULT '[]',
    remediation_steps            JSONB NOT NULL DEFAULT '[]',
    estimated_resolution_minutes INT,
    recurrence_risk              TEXT NOT NULL DEFAULT 'medium',
    recurrence_reasoning         TEXT,
    similar_incidents            JSONB NOT NULL DEFAULT '[]',
    logs_analyzed_count          INT NOT NULL DEFAULT 0,
    deployments_checked_count    INT NOT NULL DEFAULT 0,
    runbook_markdown             TEXT,
    chroma_doc_id                TEXT
);

CREATE INDEX idx_rca_incident ON rca_results(incident_id);

-- ── Action Audit ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS action_audit (
    audit_id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    action_id         UUID NOT NULL,
    incident_id       UUID NOT NULL REFERENCES incidents(incident_id),
    action_type       TEXT NOT NULL,
    status            TEXT NOT NULL,
    parameters        JSONB NOT NULL DEFAULT '{}',
    started_at        TIMESTAMPTZ,
    completed_at      TIMESTAMPTZ,
    duration_seconds  FLOAT,
    state_before      JSONB NOT NULL DEFAULT '{}',
    state_after       JSONB NOT NULL DEFAULT '{}',
    diff_summary      TEXT,
    executed_by       TEXT NOT NULL DEFAULT 'system',
    approved_by       TEXT,
    output            TEXT,
    error             TEXT,
    rolled_back       BOOLEAN NOT NULL DEFAULT FALSE,
    rollback_audit_id UUID,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_incident ON action_audit(incident_id);
CREATE INDEX idx_audit_status   ON action_audit(status);

-- ── Runbooks ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS runbooks (
    runbook_id   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    title        TEXT NOT NULL,
    service_name TEXT NOT NULL,
    markdown     TEXT NOT NULL,
    version      INT NOT NULL DEFAULT 1,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by   TEXT NOT NULL DEFAULT 'system',
    tags         JSONB NOT NULL DEFAULT '[]'
);

-- ── SLO Definitions ────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS slo_definitions (
    slo_id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name             TEXT NOT NULL,
    service_name     TEXT NOT NULL,
    slo_type         TEXT NOT NULL,
    target_percentage FLOAT NOT NULL,
    window_days      INT NOT NULL DEFAULT 30,
    metric_query     TEXT NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Alert Rules ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alert_rules (
    rule_id      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name         TEXT NOT NULL,
    service_name TEXT NOT NULL,
    metric_type  TEXT NOT NULL,
    condition    TEXT NOT NULL,   -- e.g. "> 0.8"
    threshold    FLOAT NOT NULL,
    severity     VARCHAR(2) NOT NULL DEFAULT 'P3',
    enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Model Performance History ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS model_performance (
    id              SERIAL PRIMARY KEY,
    model_type      TEXT NOT NULL,  -- lstm | isolation_forest | prophet
    model_version   TEXT NOT NULL,
    evaluated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    precision_score FLOAT,
    recall_score    FLOAT,
    f1_score        FLOAT,
    fpr             FLOAT,   -- false positive rate
    fnr             FLOAT,   -- false negative rate
    auc_roc         FLOAT,
    promoted        BOOLEAN NOT NULL DEFAULT FALSE,
    notes           TEXT
);

-- ── Users ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    user_id       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email         TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    full_name     TEXT,
    role          TEXT NOT NULL DEFAULT 'viewer',  -- viewer | operator | admin
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);

-- ── Integration Status ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS integration_status (
    integration_name TEXT PRIMARY KEY,
    integration_type TEXT NOT NULL,   -- cloud | devops
    enabled          BOOLEAN NOT NULL DEFAULT FALSE,
    last_sync_at     TIMESTAMPTZ,
    last_error       TEXT,
    error_count      INT NOT NULL DEFAULT 0,
    events_ingested  BIGINT NOT NULL DEFAULT 0,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Default admin user (password: changeme — MUST be changed via API after first login)
INSERT INTO users (email, hashed_password, full_name, role)
VALUES (
    'admin@neuralops.local',
    '$2b$12$EIXkZHv8D4Y/wbnZFHmhq.vkf3Dz2sI5.RtFSuO6hS.WFJJ.vS1Gu',  -- bcrypt of 'changeme'
    'NeuralOps Admin',
    'admin'
) ON CONFLICT (email) DO NOTHING;
