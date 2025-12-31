-- AegisAI PostgreSQL Initialization Script

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Events table (existing)
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    track_id INTEGER,
    risk_level VARCHAR(20),
    risk_score REAL,
    message TEXT NOT NULL,
    factors JSONB,
    zone VARCHAR(50),
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Alerts table (existing)
CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    event_id INTEGER NOT NULL REFERENCES events(id),
    level VARCHAR(20) NOT NULL,
    acknowledged BOOLEAN DEFAULT FALSE,
    acknowledged_at TIMESTAMPTZ,
    acknowledged_by VARCHAR(100),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Track statistics table (existing)
CREATE TABLE IF NOT EXISTS track_stats (
    track_id INTEGER PRIMARY KEY,
    class_name VARCHAR(50) NOT NULL,
    first_seen TIMESTAMPTZ NOT NULL,
    last_seen TIMESTAMPTZ NOT NULL,
    total_frames INTEGER DEFAULT 0,
    max_risk_score REAL DEFAULT 0.0,
    behaviors_detected JSONB DEFAULT '[]'
);

-- Sessions table (existing)
CREATE TABLE IF NOT EXISTS sessions (
    id SERIAL PRIMARY KEY,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    total_frames INTEGER DEFAULT 0,
    total_detections INTEGER DEFAULT 0,
    total_tracks INTEGER DEFAULT 0,
    total_alerts INTEGER DEFAULT 0,
    avg_fps REAL DEFAULT 0.0
);

-- =========================================
-- NEW: Intelligence Module Tables
-- =========================================

-- Behavioral Sessions (Analytics)
CREATE TABLE IF NOT EXISTS behavioral_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id VARCHAR(100) UNIQUE NOT NULL,
    user_hash VARCHAR(64),
    intent VARCHAR(30),
    scroll_depth_max REAL DEFAULT 0.0,
    rage_clicks INTEGER DEFAULT 0,
    hesitation_count INTEGER DEFAULT 0,
    decision_path JSONB DEFAULT '[]',
    event_count INTEGER DEFAULT 0,
    churn_probability REAL,
    conversion_probability REAL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Behavior Events (Analytics)
CREATE TABLE IF NOT EXISTS behavior_events (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    properties JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Behavior Embeddings (Analytics)
CREATE TABLE IF NOT EXISTS behavior_embeddings (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(100) UNIQUE NOT NULL,
    embedding REAL[] NOT NULL,
    cluster_id INTEGER,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Telemetry Spans (Observability)
CREATE TABLE IF NOT EXISTS telemetry_spans (
    id SERIAL PRIMARY KEY,
    trace_id VARCHAR(100) NOT NULL,
    span_id VARCHAR(100) NOT NULL,
    parent_id VARCHAR(100),
    name VARCHAR(200) NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ,
    duration_ms REAL,
    status VARCHAR(20) DEFAULT 'ok',
    attributes JSONB DEFAULT '{}',
    events JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Telemetry Metrics (Observability)
CREATE TABLE IF NOT EXISTS telemetry_metrics (
    id SERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    value REAL NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    labels JSONB DEFAULT '{}',
    unit VARCHAR(30),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Anomalies (Observability)
CREATE TABLE IF NOT EXISTS anomalies (
    id SERIAL PRIMARY KEY,
    anomaly_type VARCHAR(50) NOT NULL,
    severity VARCHAR(20) NOT NULL,
    metric_name VARCHAR(200) NOT NULL,
    current_value REAL NOT NULL,
    expected_value REAL NOT NULL,
    deviation REAL NOT NULL,
    context JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Smart Alerts (Observability)
CREATE TABLE IF NOT EXISTS smart_alerts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_id VARCHAR(100) UNIQUE NOT NULL,
    title VARCHAR(300) NOT NULL,
    description TEXT NOT NULL,
    priority INTEGER NOT NULL,
    status VARCHAR(30) DEFAULT 'open',
    root_cause JSONB,
    related_metrics JSONB DEFAULT '[]',
    auto_heal_attempted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMPTZ
);

-- NLQ Queries (Product Intelligence)
CREATE TABLE IF NOT EXISTS nlq_queries (
    id SERIAL PRIMARY KEY,
    query TEXT NOT NULL,
    query_type VARCHAR(30) NOT NULL,
    answer TEXT NOT NULL,
    confidence REAL NOT NULL,
    data JSONB,
    sql_generated TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Insights (Product Intelligence)
CREATE TABLE IF NOT EXISTS insights (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    insight_id VARCHAR(100) UNIQUE NOT NULL,
    insight_type VARCHAR(30) NOT NULL,
    priority INTEGER NOT NULL,
    title VARCHAR(300) NOT NULL,
    description TEXT NOT NULL,
    impact TEXT,
    confidence REAL NOT NULL,
    data_points JSONB DEFAULT '[]',
    action_items JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Consent Records (Privacy)
CREATE TABLE IF NOT EXISTS consent_records (
    id SERIAL PRIMARY KEY,
    user_hash VARCHAR(64) NOT NULL,
    consent_type VARCHAR(30) NOT NULL,
    granted BOOLEAN NOT NULL,
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- =========================================
-- Indexes
-- =========================================

CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_track_id ON events(track_id);
CREATE INDEX IF NOT EXISTS idx_events_risk_level ON events(risk_level);
CREATE INDEX IF NOT EXISTS idx_alerts_level ON alerts(level);
CREATE INDEX IF NOT EXISTS idx_alerts_acknowledged ON alerts(acknowledged);

CREATE INDEX IF NOT EXISTS idx_behavioral_sessions_intent ON behavioral_sessions(intent);
CREATE INDEX IF NOT EXISTS idx_behavioral_sessions_created ON behavioral_sessions(created_at);
CREATE INDEX IF NOT EXISTS idx_behavior_events_session ON behavior_events(session_id);
CREATE INDEX IF NOT EXISTS idx_behavior_events_type ON behavior_events(event_type);
CREATE INDEX IF NOT EXISTS idx_behavior_embeddings_cluster ON behavior_embeddings(cluster_id);

CREATE INDEX IF NOT EXISTS idx_telemetry_spans_trace ON telemetry_spans(trace_id);
CREATE INDEX IF NOT EXISTS idx_telemetry_metrics_name ON telemetry_metrics(name);
CREATE INDEX IF NOT EXISTS idx_telemetry_metrics_timestamp ON telemetry_metrics(timestamp);
CREATE INDEX IF NOT EXISTS idx_anomalies_type ON anomalies(anomaly_type);
CREATE INDEX IF NOT EXISTS idx_smart_alerts_status ON smart_alerts(status);

CREATE INDEX IF NOT EXISTS idx_nlq_queries_type ON nlq_queries(query_type);
CREATE INDEX IF NOT EXISTS idx_insights_type ON insights(insight_type);
CREATE INDEX IF NOT EXISTS idx_consent_records_user ON consent_records(user_hash);
