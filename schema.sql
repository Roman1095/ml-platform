-- ML Training Platform
-- PostgreSQL schema
-- Initial schema, designed for extension via migrations.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =========================
-- ENUM TYPES
-- =========================

CREATE TYPE user_role AS ENUM (
    'user',
    'admin'
);

CREATE TYPE template_status AS ENUM (
    'draft',
    'active',
    'disabled'
);

CREATE TYPE dataset_source_type AS ENUM (
    'builtin',
    'user'
);

CREATE TYPE dataset_status AS ENUM (
    'available',
    'processing',
    'disabled',
    'failed'
);

CREATE TYPE dataset_version_status AS ENUM (
    'available',
    'processing',
    'failed',
    'disabled'
);

CREATE TYPE job_status AS ENUM (
    'queued',
    'preparing',
    'running',
    'evaluating',
    'exporting',
    'completed',
    'failed',
    'cancelled'
);

CREATE TYPE output_format AS ENUM (
    'onnx',
    'pth',
    'joblib'
);

CREATE TYPE worker_status AS ENUM (
    'online',
    'offline',
    'busy',
    'maintenance'
);

-- =========================
-- USERS
-- =========================

CREATE TABLE users (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email               VARCHAR(320) NOT NULL UNIQUE,
    password_hash       TEXT NOT NULL,
    display_name        VARCHAR(120),
    role                user_role NOT NULL DEFAULT 'user',
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at       TIMESTAMPTZ
);

CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_created_at ON users(created_at);

-- =========================
-- TRAINING TEMPLATES
-- =========================

CREATE TABLE training_templates (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                VARCHAR(120) NOT NULL,
    slug                VARCHAR(120) NOT NULL UNIQUE,
    description         TEXT,
    framework           VARCHAR(50) NOT NULL,
    task_type           VARCHAR(50) NOT NULL,
    status              template_status NOT NULL DEFAULT 'draft',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_training_templates_status ON training_templates(status);
CREATE INDEX idx_training_templates_framework ON training_templates(framework);

-- Versioning is important because a template may change while old jobs must remain reproducible.
CREATE TABLE training_template_versions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    template_id         UUID NOT NULL REFERENCES training_templates(id) ON DELETE CASCADE,
    version             INTEGER NOT NULL,
    entrypoint          VARCHAR(255) NOT NULL,
    parameter_schema    JSONB NOT NULL DEFAULT '{}'::jsonb,
    default_parameters  JSONB NOT NULL DEFAULT '{}'::jsonb,
    environment         JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(template_id, version)
);

CREATE INDEX idx_template_versions_template ON training_template_versions(template_id);
CREATE INDEX idx_template_versions_active ON training_template_versions(is_active);

-- =========================
-- DATASETS
-- =========================

CREATE TABLE datasets (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id       UUID REFERENCES users(id) ON DELETE CASCADE,
    name                VARCHAR(150) NOT NULL,
    slug                VARCHAR(150),
    source_type         dataset_source_type NOT NULL,
    status              dataset_status NOT NULL DEFAULT 'available',
    framework            VARCHAR(50) NOT NULL DEFAULT 'sklearn',
    description         TEXT,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Built-in datasets have no owner; user datasets must have one.
    CONSTRAINT datasets_owner_source_ck CHECK (
        (source_type = 'builtin' AND owner_user_id IS NULL)
        OR
        (source_type = 'user' AND owner_user_id IS NOT NULL)
    )
);

CREATE INDEX idx_datasets_owner ON datasets(owner_user_id);
CREATE INDEX idx_datasets_source_type ON datasets(source_type);
CREATE INDEX idx_datasets_status ON datasets(status);

CREATE TABLE dataset_versions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_id          UUID NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    version             INTEGER NOT NULL,
    storage_uri         TEXT,
    checksum_sha256     CHAR(64),
    size_bytes          BIGINT,
    sample_count        BIGINT,
    feature_count       INTEGER,
    target_count        INTEGER,
    metadata            JSONB NOT NULL DEFAULT '{}'::jsonb,
    status              dataset_version_status NOT NULL DEFAULT 'available',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(dataset_id, version),
    CONSTRAINT dataset_versions_size_ck CHECK (size_bytes IS NULL OR size_bytes >= 0),
    CONSTRAINT dataset_versions_sample_count_ck CHECK (sample_count IS NULL OR sample_count >= 0),
    CONSTRAINT dataset_versions_feature_count_ck CHECK (feature_count IS NULL OR feature_count >= 0),
    CONSTRAINT dataset_versions_target_count_ck CHECK (target_count IS NULL OR target_count >= 0)
);

CREATE INDEX idx_dataset_versions_dataset ON dataset_versions(dataset_id);
CREATE INDEX idx_dataset_versions_status ON dataset_versions(status);

-- =========================
-- COMPUTE / WORKER NODES
-- =========================

CREATE TABLE worker_nodes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                VARCHAR(120) NOT NULL UNIQUE,
    hostname            VARCHAR(255),
    platform            VARCHAR(50),
    architecture        VARCHAR(50),
    cpu_cores           INTEGER,
    memory_bytes        BIGINT,
    status              worker_status NOT NULL DEFAULT 'offline',
    capabilities        JSONB NOT NULL DEFAULT '{}'::jsonb,
    last_heartbeat_at   TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT worker_nodes_cpu_cores_ck CHECK (cpu_cores IS NULL OR cpu_cores > 0),
    CONSTRAINT worker_nodes_memory_ck CHECK (memory_bytes IS NULL OR memory_bytes > 0)
);

CREATE INDEX idx_worker_nodes_status ON worker_nodes(status);
CREATE INDEX idx_worker_nodes_heartbeat ON worker_nodes(last_heartbeat_at);

-- =========================
-- TRAINING JOBS
-- =========================

CREATE TABLE training_jobs (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id           UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    template_version_id     UUID NOT NULL REFERENCES training_template_versions(id),
    dataset_version_id      UUID NOT NULL REFERENCES dataset_versions(id),
    worker_node_id          UUID REFERENCES worker_nodes(id) ON DELETE SET NULL,

    name                    VARCHAR(150),
    status                  job_status NOT NULL DEFAULT 'queued',
    output_format           output_format NOT NULL,

    parameters              JSONB NOT NULL DEFAULT '{}'::jsonb,
    metrics_summary         JSONB NOT NULL DEFAULT '{}'::jsonb,

    progress_percent        NUMERIC(5,2) NOT NULL DEFAULT 0,
    current_epoch           INTEGER,
    total_epochs            INTEGER,

    error_code              VARCHAR(100),
    error_message           TEXT,

    queued_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at              TIMESTAMPTZ,
    finished_at             TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT training_jobs_progress_ck CHECK (
        progress_percent >= 0 AND progress_percent <= 100
    ),
    CONSTRAINT training_jobs_epoch_ck CHECK (
        (current_epoch IS NULL OR current_epoch >= 0)
        AND
        (total_epochs IS NULL OR total_epochs > 0)
    )
);

CREATE INDEX idx_training_jobs_owner ON training_jobs(owner_user_id);
CREATE INDEX idx_training_jobs_status ON training_jobs(status);
CREATE INDEX idx_training_jobs_worker ON training_jobs(worker_node_id);
CREATE INDEX idx_training_jobs_created_at ON training_jobs(created_at DESC);
CREATE INDEX idx_training_jobs_queue ON training_jobs(status, queued_at);

-- =========================
-- TRAINING METRICS
-- =========================

CREATE TABLE training_metrics (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id              UUID NOT NULL REFERENCES training_jobs(id) ON DELETE CASCADE,
    epoch               INTEGER,
    step                INTEGER,
    metric_name         VARCHAR(100) NOT NULL,
    metric_value        DOUBLE PRECISION NOT NULL,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT training_metrics_epoch_ck CHECK (epoch IS NULL OR epoch >= 0),
    CONSTRAINT training_metrics_step_ck CHECK (step IS NULL OR step >= 0)
);

CREATE INDEX idx_training_metrics_job ON training_metrics(job_id);
CREATE INDEX idx_training_metrics_job_epoch ON training_metrics(job_id, epoch);
CREATE INDEX idx_training_metrics_job_metric ON training_metrics(job_id, metric_name);

-- =========================
-- TRAINING LOGS
-- =========================

CREATE TABLE training_logs (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id              UUID NOT NULL REFERENCES training_jobs(id) ON DELETE CASCADE,
    level               VARCHAR(20) NOT NULL DEFAULT 'INFO',
    message             TEXT NOT NULL,
    epoch               INTEGER,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT training_logs_epoch_ck CHECK (epoch IS NULL OR epoch >= 0)
);

CREATE INDEX idx_training_logs_job_created ON training_logs(job_id, created_at);
CREATE INDEX idx_training_logs_job_level ON training_logs(job_id, level);

-- =========================
-- MODEL ARTIFACTS
-- =========================

CREATE TABLE model_artifacts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id              UUID NOT NULL REFERENCES training_jobs(id) ON DELETE CASCADE,
    owner_user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    name                VARCHAR(150) NOT NULL,
    version             INTEGER NOT NULL DEFAULT 1,
    format              output_format NOT NULL,
    storage_uri         TEXT NOT NULL,
    checksum_sha256     CHAR(64),
    size_bytes          BIGINT,

    metrics              JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata             JSONB NOT NULL DEFAULT '{}'::jsonb,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    UNIQUE(job_id, format),
    CONSTRAINT model_artifacts_size_ck CHECK (size_bytes IS NULL OR size_bytes >= 0),
    CONSTRAINT model_artifacts_version_ck CHECK (version > 0)
);

CREATE INDEX idx_model_artifacts_owner ON model_artifacts(owner_user_id);
CREATE INDEX idx_model_artifacts_job ON model_artifacts(job_id);
CREATE INDEX idx_model_artifacts_created_at ON model_artifacts(created_at DESC);

-- =========================
-- OPTIONAL: USER SESSIONS
-- =========================
-- Kept in the initial schema because a personal cabinet normally needs
-- revocable server-side sessions even if JWT is used for access tokens.

CREATE TABLE user_sessions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    refresh_token_hash  TEXT NOT NULL UNIQUE,
    expires_at          TIMESTAMPTZ NOT NULL,
    revoked_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at        TIMESTAMPTZ
);

CREATE INDEX idx_user_sessions_user ON user_sessions(user_id);
CREATE INDEX idx_user_sessions_expires ON user_sessions(expires_at);

-- =========================
-- BUSINESS INTEGRITY RULES
-- =========================

-- Prevent duplicate current-looking versions from becoming ambiguous.
CREATE UNIQUE INDEX uq_active_template_version
    ON training_template_versions(template_id)
    WHERE is_active = TRUE;

-- Only one row per (job, metric, epoch, step) is not enforced because
-- some trainers emit multiple measurements for the same step/metric.

-- =========================
-- COMMENTS
-- =========================

COMMENT ON TABLE users IS 'Platform users and administrators.';
COMMENT ON TABLE training_templates IS 'Reusable training templates exposed in the UI.';
COMMENT ON TABLE training_template_versions IS 'Immutable versioned definitions of training templates.';
COMMENT ON TABLE datasets IS 'Dataset catalog; supports built-in and future user datasets.';
COMMENT ON TABLE dataset_versions IS 'Versioned dataset metadata and storage references.';
COMMENT ON TABLE worker_nodes IS 'Training-capable machines, initially the Raspberry Pi 5.';
COMMENT ON TABLE training_jobs IS 'User-submitted training runs and their immutable configuration.';
COMMENT ON TABLE training_metrics IS 'Time-series metrics produced during a training job.';
COMMENT ON TABLE training_logs IS 'Human-readable logs for a training job.';
COMMENT ON TABLE model_artifacts IS 'Metadata for trained model files stored outside PostgreSQL.';
COMMENT ON TABLE user_sessions IS 'Revocable refresh-token sessions for user accounts.';

COMMENT ON COLUMN training_jobs.parameters IS 'Exact parameters used by this run; preserved as JSONB for reproducibility and future extensibility.';
COMMENT ON COLUMN training_jobs.metrics_summary IS 'Final/summary metrics cached for fast UI display.';
COMMENT ON COLUMN model_artifacts.storage_uri IS 'Path/URI to the actual model file; binary artifacts are not stored in PostgreSQL.';
COMMENT ON COLUMN datasets.metadata IS 'Dataset-specific metadata, e.g. class names or sklearn dataset identifiers.';
