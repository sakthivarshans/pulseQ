-- NeuralOps PostgreSQL schema — complete definition
-- Runs once on first container start via docker-entrypoint-initdb.d
-- All tables, indexes, seed data in dependency order.

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- ── Users ──────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    user_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email           TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    full_name       TEXT,
    role            TEXT NOT NULL DEFAULT 'viewer',  -- viewer | operator | admin
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at   TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ── Repositories ───────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS repositories (
    id                          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name                        TEXT NOT NULL,
    owner                       TEXT NOT NULL,
    repo_url                    TEXT NOT NULL UNIQUE,
    platform                    TEXT NOT NULL DEFAULT 'github',  -- github | gitlab | bitbucket
    status                      TEXT NOT NULL DEFAULT 'connected',  -- connected | scanning | error | disconnected
    is_default                  BOOLEAN NOT NULL DEFAULT FALSE,
    is_live_monitoring_enabled  BOOLEAN NOT NULL DEFAULT FALSE,
    website_url                 TEXT,
    last_commit_hash            TEXT,
    last_commit_at              TIMESTAMPTZ,
    last_scanned_at             TIMESTAMPTZ,
    consecutive_failures        INT NOT NULL DEFAULT 0,
    total_files                 INT,
    total_loc                   INT,
    language                    TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_repos_owner_name ON repositories(owner, name);
CREATE INDEX IF NOT EXISTS idx_repos_status     ON repositories(status);
CREATE INDEX IF NOT EXISTS idx_repos_is_default ON repositories(is_default);

-- ── Incidents ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS incidents (
    incident_id             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    repo_id                 UUID REFERENCES repositories(id) ON DELETE SET NULL,
    title                   TEXT NOT NULL,
    description             TEXT,
    severity                VARCHAR(2) NOT NULL,   -- P1-P4
    status                  VARCHAR(20) NOT NULL DEFAULT 'detected',
    detected_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    investigating_at        TIMESTAMPTZ,
    remediating_at          TIMESTAMPTZ,
    resolved_at             TIMESTAMPTZ,
    post_mortem_at          TIMESTAMPTZ,
    primary_service         TEXT NOT NULL,
    affected_services       JSONB NOT NULL DEFAULT '[]',
    blast_radius            JSONB,
    environment             TEXT NOT NULL DEFAULT 'production',
    cloud_provider          TEXT NOT NULL DEFAULT 'unknown',
    region                  TEXT,
    correlated_anomaly_ids  JSONB NOT NULL DEFAULT '[]',
    peak_anomaly_score      FLOAT NOT NULL DEFAULT 0,
    ml_confidence           FLOAT NOT NULL DEFAULT 0,
    rca_id                  UUID,
    action_ids              JSONB NOT NULL DEFAULT '[]',
    pagerduty_incident_id   TEXT,
    slack_thread_ts         TEXT,
    jira_ticket_key         TEXT,
    mttr_minutes            FLOAT,
    is_false_positive       BOOLEAN NOT NULL DEFAULT FALSE,
    runbook_id              UUID,
    labels                  JSONB NOT NULL DEFAULT '{}',
    acknowledged_by         TEXT,
    root_cause_summary      TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_incidents_status    ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_severity  ON incidents(severity);
CREATE INDEX IF NOT EXISTS idx_incidents_detected  ON incidents(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_incidents_service   ON incidents(primary_service);
CREATE INDEX IF NOT EXISTS idx_incidents_repo_id   ON incidents(repo_id);

-- ── RCA Results ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS rca_results (
    rca_id                          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id                     UUID NOT NULL REFERENCES incidents(incident_id),
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    llm_provider_used               TEXT NOT NULL,
    root_cause_summary              TEXT NOT NULL,
    root_cause_confidence           FLOAT NOT NULL,
    primary_contributing_factor     TEXT NOT NULL,
    secondary_contributing_factors  JSONB NOT NULL DEFAULT '[]',
    affected_components             JSONB NOT NULL DEFAULT '[]',
    remediation_steps               JSONB NOT NULL DEFAULT '[]',
    estimated_resolution_minutes    INT,
    recurrence_risk                 TEXT NOT NULL DEFAULT 'medium',
    recurrence_reasoning            TEXT,
    similar_incidents               JSONB NOT NULL DEFAULT '[]',
    logs_analyzed_count             INT NOT NULL DEFAULT 0,
    deployments_checked_count       INT NOT NULL DEFAULT 0,
    runbook_markdown                TEXT,
    chroma_doc_id                   TEXT
);

CREATE INDEX IF NOT EXISTS idx_rca_incident ON rca_results(incident_id);

-- ── Action Audit ───────────────────────────────────────────────────────────────
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

CREATE INDEX IF NOT EXISTS idx_audit_incident ON action_audit(incident_id);
CREATE INDEX IF NOT EXISTS idx_audit_status   ON action_audit(status);

-- ── Runbooks ───────────────────────────────────────────────────────────────────
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

-- ── SLO Definitions ────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS slo_definitions (
    slo_id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name              TEXT NOT NULL,
    service_name      TEXT NOT NULL,
    slo_type          TEXT NOT NULL,
    target_percentage FLOAT NOT NULL,
    window_days       INT NOT NULL DEFAULT 30,
    metric_query      TEXT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Alert Rules ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS alert_rules (
    rule_id      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name         TEXT NOT NULL,
    service_name TEXT NOT NULL,
    metric_type  TEXT NOT NULL,
    condition    TEXT NOT NULL,
    threshold    FLOAT NOT NULL,
    severity     VARCHAR(2) NOT NULL DEFAULT 'P3',
    enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Model Performance History ──────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS model_performance (
    id              SERIAL PRIMARY KEY,
    model_type      TEXT NOT NULL,
    model_version   TEXT NOT NULL,
    evaluated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    precision_score FLOAT,
    recall_score    FLOAT,
    f1_score        FLOAT,
    fpr             FLOAT,
    fnr             FLOAT,
    auc_roc         FLOAT,
    promoted        BOOLEAN NOT NULL DEFAULT FALSE,
    notes           TEXT
);

-- ── Integration Status ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS integration_status (
    integration_name TEXT PRIMARY KEY,
    integration_type TEXT NOT NULL,
    enabled          BOOLEAN NOT NULL DEFAULT FALSE,
    last_sync_at     TIMESTAMPTZ,
    last_error       TEXT,
    error_count      INT NOT NULL DEFAULT 0,
    events_ingested  BIGINT NOT NULL DEFAULT 0,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Notifications ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS notifications (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID REFERENCES users(user_id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    message     TEXT NOT NULL,
    type        TEXT NOT NULL DEFAULT 'info',   -- info | warning | error | success
    is_read     BOOLEAN NOT NULL DEFAULT FALSE,
    link        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notifications_user_id  ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_is_read  ON notifications(is_read);
CREATE INDEX IF NOT EXISTS idx_notifications_created  ON notifications(created_at DESC);

-- ── Website Checks ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS website_checks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    repo_id         UUID REFERENCES repositories(id) ON DELETE CASCADE,
    url             TEXT NOT NULL,
    status_code     INT,
    response_ms     FLOAT,
    is_up           BOOLEAN NOT NULL DEFAULT TRUE,
    error           TEXT,
    checked_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_website_checks_repo_id ON website_checks(repo_id);
CREATE INDEX IF NOT EXISTS idx_website_checks_checked ON website_checks(checked_at DESC);

-- ── Metrics ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS metrics (
    id              BIGSERIAL PRIMARY KEY,
    service_name    TEXT NOT NULL DEFAULT 'system',
    metric_type     TEXT NOT NULL,
    value           FLOAT NOT NULL,
    unit            TEXT,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    labels          JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_metrics_service_ts ON metrics(service_name, ts DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_type_ts    ON metrics(metric_type, ts DESC);

-- ── Incident History View ──────────────────────────────────────────────────────
CREATE OR REPLACE VIEW incident_history_view AS
    SELECT
        i.incident_id,
        i.title,
        i.severity,
        i.status,
        i.detected_at,
        i.resolved_at,
        i.mttr_minutes,
        i.primary_service,
        i.root_cause_summary,
        i.is_false_positive,
        r.name        AS repo_name,
        r.owner       AS repo_owner,
        r.platform    AS repo_platform
    FROM incidents i
    LEFT JOIN repositories r ON r.id = i.repo_id
    ORDER BY i.detected_at DESC;

-- ────────────────────────────────────────────────────────────────────────────────
-- SEED DATA
-- ────────────────────────────────────────────────────────────────────────────────

-- Admin user  (email: admin@neuralops.io  password: Admin@123)
-- bcrypt hash generated with: python -c "from passlib.context import CryptContext; print(CryptContext(['bcrypt']).hash('Admin@123'))"
INSERT INTO users (email, hashed_password, full_name, role)
VALUES (
    'admin@neuralops.io',
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewWK3.bFnLuJm5Mu',
    'NeuralOps Admin',
    'admin'
) ON CONFLICT (email) DO NOTHING;

-- Three default demo repositories (is_default = TRUE so they always appear in the dropdown)
INSERT INTO repositories (name, owner, repo_url, platform, status, is_default, language)
VALUES
    ('neuralops-demo',    'neuralops-team', 'https://github.com/neuralops-team/neuralops-demo',    'github', 'connected', TRUE, 'Python'),
    ('api-gateway',       'neuralops-team', 'https://github.com/neuralops-team/api-gateway',       'github', 'connected', TRUE, 'Go'),
    ('ml-pipeline',       'neuralops-team', 'https://github.com/neuralops-team/ml-pipeline',       'github', 'connected', TRUE, 'Python')
ON CONFLICT (repo_url) DO NOTHING;

-- ── Add optional columns to repositories if missing ────────────────────────────
ALTER TABLE repositories
    ADD COLUMN IF NOT EXISTS description TEXT,
    ADD COLUMN IF NOT EXISTS primary_language TEXT;

-- ── Predictions table ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS predictions (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    repo_id                 UUID REFERENCES repositories(id) ON DELETE CASCADE,
    service_name            TEXT NOT NULL DEFAULT 'unknown',
    prediction_type         TEXT NOT NULL,
    description             TEXT,
    confidence              FLOAT NOT NULL DEFAULT 0.5,
    status                  TEXT NOT NULL DEFAULT 'active',
    estimated_impact_time   TIMESTAMPTZ,
    snoozed_until           TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_predictions_repo_id  ON predictions(repo_id);
CREATE INDEX IF NOT EXISTS idx_predictions_status   ON predictions(status);
CREATE INDEX IF NOT EXISTS idx_predictions_created  ON predictions(created_at DESC);

-- ── Three permanent sakthivarshans repositories (fixed UUIDs, never deleted) ────
INSERT INTO repositories (
    id, name, owner, repo_url, platform, description,
    primary_language, is_default, status, created_at
) VALUES
(
    '00000000-0000-0000-0000-000000000001',
    'Bug-Detection-and-Fixing-Model',
    'sakthivarshans',
    'https://github.com/sakthivarshans/Bug-Detection-and-Fixing-Model.git',
    'github',
    'Bug Detection and Fixing Model',
    'Python',
    true,
    'connected',
    NOW()
),
(
    '00000000-0000-0000-0000-000000000002',
    'Diabetes-Prediction-Model',
    'sakthivarshans',
    'https://github.com/sakthivarshans/Diabetes-Prediction-Model.git',
    'github',
    'Diabetes Prediction Model',
    'Python',
    true,
    'connected',
    NOW()
),
(
    '00000000-0000-0000-0000-000000000003',
    'Noether-Duplicated',
    'sakthivarshans',
    'https://github.com/sakthivarshans/Noether-Duplicated.git',
    'github',
    'Noether Duplicated Project',
    'Python',
    true,
    'connected',
    NOW()
)
ON CONFLICT (repo_url) DO NOTHING;

-- ── Seed predictions linked to the three default repositories ───────────────────
INSERT INTO predictions (
    repo_id, service_name, prediction_type,
    description, confidence, status, estimated_impact_time, created_at
) VALUES
(
    '00000000-0000-0000-0000-000000000001',
    'Bug-Detection-and-Fixing-Model',
    'high_error_rate',
    'Error rate trending upward in bug detection pipeline. Model inference failures expected to increase.',
    0.87,
    'active',
    NOW() + INTERVAL '2 hours',
    NOW()
),
(
    '00000000-0000-0000-0000-000000000002',
    'Diabetes-Prediction-Model',
    'memory_exhaustion',
    'Memory usage growing during batch prediction. OOM risk if dataset size increases.',
    0.79,
    'active',
    NOW() + INTERVAL '4 hours',
    NOW()
),
(
    '00000000-0000-0000-0000-000000000003',
    'Noether-Duplicated',
    'cpu_spike',
    'CPU usage elevated during duplicate detection runs. Performance degradation expected under load.',
    0.91,
    'active',
    NOW() + INTERVAL '1 hour',
    NOW()
)
ON CONFLICT DO NOTHING;

-- ── Seed incidents linked to the three default repositories ─────────────────────
INSERT INTO incidents (
    repo_id, title, severity, status,
    primary_service, affected_services, root_cause_summary, detected_at, created_at
) VALUES
(
    '00000000-0000-0000-0000-000000000001',
    'Bug Detection Model - High False Positive Rate',
    'P2',
    'resolved',
    'Bug-Detection-and-Fixing-Model',
    '["Bug-Detection-and-Fixing-Model"]',
    'Model threshold misconfiguration causing false positives in production',
    NOW() - INTERVAL '2 days',
    NOW() - INTERVAL '2 days'
),
(
    '00000000-0000-0000-0000-000000000002',
    'Diabetes Model - Prediction Latency Spike',
    'P3',
    'resolved',
    'Diabetes-Prediction-Model',
    '["Diabetes-Prediction-Model"]',
    'Unoptimized feature preprocessing causing 3x latency increase',
    NOW() - INTERVAL '5 days',
    NOW() - INTERVAL '5 days'
),
(
    '00000000-0000-0000-0000-000000000003',
    'Noether - Duplicate Detection Failure',
    'P1',
    'resolved',
    'Noether-Duplicated',
    '["Noether-Duplicated"]',
    'Hash collision in deduplication algorithm causing missed duplicates',
    NOW() - INTERVAL '1 day',
    NOW() - INTERVAL '1 day'
)
ON CONFLICT DO NOTHING;

