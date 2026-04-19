-- Thinking OS — DDL Reference (TASK-141)
-- This file is documentation only. Actual schema is applied by db.py migrations.
-- Source of truth: db.py MIGRATIONS list.

-- === Migration v1 (TASK-141) ===

CREATE TABLE schema_version (
    version     INTEGER PRIMARY KEY,
    description TEXT,
    applied_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE task_outcomes (
    task_id     TEXT PRIMARY KEY,
    type        TEXT NOT NULL,
    domain      TEXT NOT NULL,
    complexity  TEXT NOT NULL,
    dimensions  INTEGER DEFAULT 1,
    outcome     TEXT NOT NULL,
    duration_min INTEGER,
    model       TEXT,
    skills_used TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE agent_metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id     TEXT,
    agent_type  TEXT NOT NULL,
    model       TEXT,
    duration_ms INTEGER,
    domain      TEXT,
    complexity  TEXT,
    outcome     TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE learned_patterns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern         TEXT NOT NULL,
    memory_type     TEXT DEFAULT 'pattern',    -- pattern/workflow/error/decision
    domain          TEXT,                       -- BACKEND/FRONTEND/INFRA/etc.
    source          TEXT,
    confidence      REAL DEFAULT 0.5,
    decay_rate      REAL DEFAULT 0.1,
    impact_score    REAL DEFAULT 0.5,          -- 0.0-1.0 digital amygdala
    concepts        TEXT,                       -- JSON array for spreading activation
    times_validated INTEGER DEFAULT 0,
    times_violated  INTEGER DEFAULT 0,
    access_count    INTEGER DEFAULT 0,
    last_accessed_at DATETIME,
    promoted_to     TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_validated  DATETIME
);

CREATE TABLE experiment_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         TEXT,
    hypothesis      TEXT NOT NULL,
    test_description TEXT,
    outcome         TEXT,
    learning        TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE observations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT,
    tool_name       TEXT,
    observation_type TEXT,
    memory_type     TEXT DEFAULT 'discovery',
    impact_score    REAL DEFAULT 0.5,
    title           TEXT,
    narrative       TEXT,
    facts           TEXT,
    concepts        TEXT,
    files_read      TEXT,
    files_modified  TEXT,
    content_hash    TEXT,
    cost_tokens     INTEGER DEFAULT 0,
    expires_at      DATETIME,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE session_summaries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT,
    task_id     TEXT,
    request     TEXT,
    investigated TEXT,
    learned     TEXT,
    completed   TEXT,
    next_steps  TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- === Migration v2 (TASK-152): FTS5 — see TASK-152 ===
-- CREATE VIRTUAL TABLE observations_fts USING fts5(title, narrative, concepts, content=observations, content_rowid=id);

-- === Migration v3 (TASK-148): routing_weights — see TASK-148 ===

-- === Migration v4: Brain features ===

CREATE TABLE outcome_history (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id                 TEXT NOT NULL,
    outcome                 TEXT NOT NULL,
    previous_outcome        TEXT,
    is_breakthrough         INTEGER DEFAULT 0,
    narrative_what_failed   TEXT,
    narrative_what_worked   TEXT,
    narrative_key_insight   TEXT,
    triggered_by            TEXT,
    created_at              DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE concept_graph (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,
    target      TEXT NOT NULL,
    edge_type   TEXT NOT NULL,
    weight      REAL DEFAULT 1.0,
    evidence    TEXT,
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source, target, edge_type)
);

-- session_summaries gains: previous_session_id, duration_minutes, files_touched,
-- observations_count, breakthrough_ids

-- Confidence scale reference (see db.py for formulas):
--   0.1: floor (never below)     0.1-0.3: weak/archived
--   0.3-0.5: emerging            0.5-0.7: moderate
--   0.7-0.9: strong              0.9-0.95: validated only
--   1.0: never assigned
