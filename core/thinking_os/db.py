"""
Coding OS — SQLite database module with auto-migration.

Provides connection management (WAL mode), schema versioning,
and migration execution for the thinking_os self-learning system.

Agent-agnostic: DB path is configurable via COS_DB_PATH env var.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Generator, Union

logger = logging.getLogger("coding_os.db")

# Default DB path — configurable via COS_DB_PATH env var
# Falls back to .coding-os/coding-os.db in current working directory.
# Canonical filename, single source of truth for every consumer (MCP server,
# Hub web, every CLI subcommand, every hook).
DB_FILENAME = "coding-os.db"
LEGACY_DB_FILENAME = "thinking_os.db"  # rename target for migrate_legacy_db_filename()
DEFAULT_DB_PATH = Path(
    os.environ.get("COS_DB_PATH", "")
    or str(Path.cwd() / ".coding-os" / DB_FILENAME)
)


def migrate_legacy_db_filename(target: Path) -> bool:
    """Rename `<dir>/thinking_os.db` → `<dir>/coding-os.db` once, in place.

    PURPOSE:      Backward-compat for projects initialised before the
                  2026-04-30 rename. Runs at the top of init_db() so the
                  first cos invocation in a project after the upgrade
                  silently relocates the file (plus its -shm / -wal
                  sidecars). No data loss; idempotent.
    INPUT:        target — desired path (e.g. .coding-os/coding-os.db).
    OUTPUT:       True when a rename happened; False when nothing to do.
    NOTES:        Only fires when target.exists() is False AND the legacy
                  sibling exists — never overwrites an already-renamed DB.
    """
    if target.exists():
        return False
    legacy = target.with_name(LEGACY_DB_FILENAME)
    if not legacy.exists():
        return False
    legacy.rename(target)
    for ext in ("-shm", "-wal"):
        legacy_aux = legacy.with_name(legacy.name + ext)
        if legacy_aux.exists():
            legacy_aux.rename(target.with_name(target.name + ext))
    logger.info("Migrated legacy DB filename: %s -> %s", legacy.name, target.name)
    return True

# ---------------------------------------------------------------------------
# FTS5 detection (must be defined before migrations that use it)
# ---------------------------------------------------------------------------

def has_fts5(conn: sqlite3.Connection) -> bool:
    """Check whether the current SQLite build supports FTS5."""
    try:
        conn.execute("CREATE VIRTUAL TABLE _fts5_probe USING fts5(x)")
        conn.execute("DROP TABLE _fts5_probe")
        return True
    except sqlite3.OperationalError:
        return False


def has_fts5_table(conn: sqlite3.Connection) -> bool:
    """Check whether the observations_fts table exists (FTS5 was successfully created)."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='observations_fts'"
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Callable migrations (defined before MIGRATIONS list so they can be referenced directly)
# ---------------------------------------------------------------------------

def _migrate_v2_fts5(conn: sqlite3.Connection) -> None:
    """Migration v2: create FTS5 virtual table and sync triggers.

    Gracefully degrades if FTS5 is not available — logs a warning and skips.
    """
    if not has_fts5(conn):
        logger.warning(
            "FTS5 not available in this SQLite build — skipping FTS5 table creation. "
            "Search will fall back to LIKE queries."
        )
        return

    conn.executescript("""\
CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts USING fts5(
    title, narrative, concepts,
    content='observations', content_rowid='id'
);

-- Auto-populate on INSERT
CREATE TRIGGER IF NOT EXISTS observations_ai AFTER INSERT ON observations BEGIN
    INSERT INTO observations_fts(rowid, title, narrative, concepts)
    VALUES (new.id, new.title, new.narrative, new.concepts);
END;

-- Re-sync on UPDATE (needed for TASK-155 compression)
CREATE TRIGGER IF NOT EXISTS observations_au AFTER UPDATE ON observations BEGIN
    INSERT INTO observations_fts(observations_fts, rowid, title, narrative, concepts)
    VALUES ('delete', old.id, old.title, old.narrative, old.concepts);
    INSERT INTO observations_fts(rowid, title, narrative, concepts)
    VALUES (new.id, new.title, new.narrative, new.concepts);
END;

-- Auto-cleanup on DELETE
CREATE TRIGGER IF NOT EXISTS observations_ad AFTER DELETE ON observations BEGIN
    INSERT INTO observations_fts(observations_fts, rowid, title, narrative, concepts)
    VALUES ('delete', old.id, old.title, old.narrative, old.concepts);
END;
""")
    logger.info("FTS5 observations_fts table and triggers created successfully")


# ---------------------------------------------------------------------------
# Migration registry
# ---------------------------------------------------------------------------
# Each migration is a (version, description, sql_or_callable) tuple.
# sql_or_callable is either a SQL string (executed via executescript)
# or a callable(conn) for migrations needing runtime logic (e.g. FTS5 check).
# Migrations MUST be append-only — never edit an applied migration.
MigrationAction = Union[str, Callable[[sqlite3.Connection], None]]


def _migrate_v4_brain_features(conn: sqlite3.Connection) -> None:
    """Migration v4: outcome_history, concept_graph, session_summaries enrichment."""

    # 1. outcome_history — append-only log of every outcome transition
    conn.executescript("""\
CREATE TABLE IF NOT EXISTS outcome_history (
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

CREATE INDEX IF NOT EXISTS idx_outcome_history_task
    ON outcome_history(task_id);
CREATE INDEX IF NOT EXISTS idx_outcome_history_breakthrough
    ON outcome_history(is_breakthrough) WHERE is_breakthrough = 1;

-- 2. concept_graph — lightweight adjacency list for file/concept relationships
CREATE TABLE IF NOT EXISTS concept_graph (
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

CREATE INDEX IF NOT EXISTS idx_concept_graph_source ON concept_graph(source);
CREATE INDEX IF NOT EXISTS idx_concept_graph_target ON concept_graph(target);
CREATE INDEX IF NOT EXISTS idx_concept_graph_type ON concept_graph(edge_type);
""")

    # 3. session_summaries enrichment — add columns if missing
    existing_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(session_summaries)").fetchall()
    }
    new_columns = [
        ("previous_session_id", "TEXT"),
        ("duration_minutes", "INTEGER"),
        ("files_touched", "TEXT"),
        ("observations_count", "INTEGER DEFAULT 0"),
        ("breakthrough_ids", "TEXT"),
    ]
    for col_name, col_type in new_columns:
        if col_name not in existing_columns:
            conn.execute(f"ALTER TABLE session_summaries ADD COLUMN {col_name} {col_type}")

    logger.info("Brain features migration v4 applied: outcome_history, concept_graph, session_summaries enrichment")


def _migrate_v5_rag(conn: sqlite3.Connection) -> None:
    """Migration v5 (Phase B): embeddings + document_chunks for RAG.

    Adds two new tables:
      - embeddings: vector storage for any source row (observations,
        learned_patterns, outcome_history, document_chunks, tasks).
        BLOB column holds float32 bytes (1536 bytes for 384-dim model).
      - document_chunks: heading-aware chunks of project docs/ for the
        document RAG knowledge base.

    Both tables are additive — no existing tables are modified. Embeddings
    are populated lazily by the embeddings module, so this migration is
    safe even when sentence-transformers is not installed.
    """
    conn.executescript("""\
CREATE TABLE IF NOT EXISTS embeddings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_table TEXT NOT NULL,
    source_id    INTEGER NOT NULL,
    text_hash    TEXT NOT NULL,
    embedding    BLOB NOT NULL,
    model_name   TEXT DEFAULT 'all-MiniLM-L6-v2',
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_table, source_id)
);

CREATE INDEX IF NOT EXISTS idx_embeddings_source
    ON embeddings(source_table, source_id);
CREATE INDEX IF NOT EXISTS idx_embeddings_model
    ON embeddings(model_name);

CREATE TABLE IF NOT EXISTS document_chunks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_path  TEXT NOT NULL,
    source_type  TEXT NOT NULL,
    chunk_index  INTEGER NOT NULL,
    heading_path TEXT,
    content      TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    priority     REAL DEFAULT 0.5,
    mtime        INTEGER NOT NULL,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_path, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_doc_chunks_path
    ON document_chunks(source_path);
CREATE INDEX IF NOT EXISTS idx_doc_chunks_type
    ON document_chunks(source_type);
""")
    logger.info("Phase B RAG migration v5 applied: embeddings + document_chunks tables created")


def has_embeddings_table(conn: sqlite3.Connection) -> bool:
    """Check whether the embeddings table exists (migration v5 applied).

    Mirrors `has_fts5_table` — used by callers that need to know whether
    semantic search is structurally available before attempting it.
    """
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='embeddings'"
    ).fetchone()
    return row is not None


def _migrate_v6_tasks(conn: sqlite3.Connection) -> None:
    """Migration v6 (Phase C): tasks table for hybrid task store.

    Mirrors the structure of `docs/tasks/TASK-###-slug.md` files as a
    queryable index. Files remain SSOT — the table is a derived cache
    populated by `task_sync.py`. Dependencies are stored as a JSON-encoded
    list so we can do `LIKE '%"TASK-195"%'` lookups for `cos_task_dependents`
    without false-positive substring matches (TASK-19 vs TASK-195).
    """
    conn.executescript("""\
CREATE TABLE IF NOT EXISTS tasks (
    task_id         TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    domain          TEXT,
    status          TEXT NOT NULL DEFAULT 'open',
    file_path       TEXT NOT NULL,
    content_hash    TEXT NOT NULL,
    mtime           INTEGER NOT NULL,
    goal_text       TEXT,
    scope_in        TEXT,
    scope_out       TEXT,
    requirements    TEXT,
    dependencies    TEXT,
    source_of_truth TEXT,
    read_first      TEXT,
    open_questions  TEXT,
    rabbit_holes    TEXT,
    verification    TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_domain ON tasks(domain);
CREATE INDEX IF NOT EXISTS idx_tasks_file_path ON tasks(file_path);
""")
    logger.info("Phase C tasks migration v6 applied: tasks table created")


def has_tasks_table(conn: sqlite3.Connection) -> bool:
    """Check whether the tasks table exists (migration v6 applied).

    Mirrors `has_fts5_table` / `has_embeddings_table` — callers can guard
    task-related queries when running against an older DB.
    """
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='tasks'"
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Phase G brain-hardening validators (shared constants)
# ---------------------------------------------------------------------------

VALID_TRUST_TIERS: frozenset[str] = frozenset({"volatile", "validated", "locked", "core"})
PROTECTED_TRUST_TIERS: frozenset[str] = frozenset({"locked", "core"})
VALID_PROVENANCE: frozenset[str] = frozenset({
    "agent_self",
    "user_directive",
    "extracted_from_outcome",
    "promoted_from_rule",
    "imported",
})


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """Return True if `column` is present in `table` per PRAGMA table_info."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()  # noqa: S608 — table names hardcoded
    return any(r[1] == column for r in rows)


def _migrate_v7_brain_hardening(conn: sqlite3.Connection) -> None:
    """Migration v7 (Phase G.1): trust_tier + provenance + memory_audit.

    PURPOSE:      Close the memory-poisoning chain (audit findings A3/A4/A8).
    INPUT:        sqlite3.Connection at schema v6.
    OUTPUT:       In-place schema upgrade to v7. No return value.
    DEPENDENCIES: learned_patterns, observations (both from v1).
    NOTES:        - Column ADDs are guarded with `_column_exists` so re-running
                    on a partially-migrated DB is safe.
                  - CHECK constraints are NOT added at the SQL level because
                    ALTER TABLE ADD COLUMN with CHECK is fragile across SQLite
                    versions. Python-side validators (VALID_TRUST_TIERS,
                    VALID_PROVENANCE) enforce at write-time in Phase G.2.
                  - Protection triggers raise `RAISE(ABORT, ...)` on any
                    UPDATE/DELETE touching a locked/core row. This is the
                    hard chokepoint — bypass is only possible through a
                    non-MCP admin helper (see plan G.1 §Risks R3).
                  - Audit log is append-only: INSERT trigger on learned_patterns
                    records every mutation. UPDATE/DELETE on memory_audit
                    itself is blocked by its own trigger.
    """
    # 1. Add trust_tier + provenance to learned_patterns (idempotent per column)
    if not _column_exists(conn, "learned_patterns", "trust_tier"):
        conn.execute(
            "ALTER TABLE learned_patterns ADD COLUMN trust_tier TEXT NOT NULL DEFAULT 'volatile'"
        )
    if not _column_exists(conn, "learned_patterns", "provenance"):
        conn.execute(
            "ALTER TABLE learned_patterns ADD COLUMN provenance TEXT NOT NULL DEFAULT 'agent_self'"
        )

    # 2. Add provenance to observations
    if not _column_exists(conn, "observations", "provenance"):
        conn.execute(
            "ALTER TABLE observations ADD COLUMN provenance TEXT NOT NULL DEFAULT 'agent_self'"
        )

    # 3. memory_audit — append-only audit log
    conn.executescript("""\
CREATE TABLE IF NOT EXISTS memory_audit (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    actor        TEXT NOT NULL,
    action       TEXT NOT NULL,
    source_table TEXT NOT NULL,
    source_id    INTEGER,
    old_value    TEXT,
    new_value    TEXT,
    reason       TEXT
);

CREATE INDEX IF NOT EXISTS idx_memory_audit_table
    ON memory_audit(source_table, source_id);
CREATE INDEX IF NOT EXISTS idx_memory_audit_created
    ON memory_audit(created_at);

-- memory_audit is append-only: block any UPDATE or DELETE
CREATE TRIGGER IF NOT EXISTS trg_memory_audit_no_update
    BEFORE UPDATE ON memory_audit
    BEGIN
        SELECT RAISE(ABORT, 'memory_audit is append-only');
    END;

CREATE TRIGGER IF NOT EXISTS trg_memory_audit_no_delete
    BEFORE DELETE ON memory_audit
    BEGIN
        SELECT RAISE(ABORT, 'memory_audit is append-only');
    END;

-- Protect locked/core patterns from UPDATE
CREATE TRIGGER IF NOT EXISTS trg_learned_patterns_protect_update
    BEFORE UPDATE ON learned_patterns
    WHEN OLD.trust_tier IN ('locked', 'core')
    BEGIN
        SELECT RAISE(ABORT, 'learned_patterns: trust_tier locked/core is immutable via standard path');
    END;

-- Protect locked/core patterns from DELETE
CREATE TRIGGER IF NOT EXISTS trg_learned_patterns_protect_delete
    BEFORE DELETE ON learned_patterns
    WHEN OLD.trust_tier IN ('locked', 'core')
    BEGIN
        SELECT RAISE(ABORT, 'learned_patterns: trust_tier locked/core cannot be deleted via standard path');
    END;
""")
    logger.info("Phase G.1 brain-hardening migration v7 applied: trust_tier, provenance, memory_audit")


def has_memory_audit_table(conn: sqlite3.Connection) -> bool:
    """Check whether the memory_audit table exists (migration v7 applied)."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_audit'"
    ).fetchone()
    return row is not None


def is_pattern_protected(conn: sqlite3.Connection, pattern_id: int) -> bool:
    """Return True if the pattern's trust_tier is in PROTECTED_TRUST_TIERS.

    PURPOSE:      Pre-flight check before calling update/delete paths to
                  avoid triggering the protection trigger as a normal flow.
    INPUT:        connection, pattern row id.
    OUTPUT:       bool. False for missing rows (they are not protected by
                  virtue of not existing).
    DEPENDENCIES: learned_patterns table, v7 schema.
    NOTES:        Callers should check this BEFORE attempting a mutation
                  and return a clean `fail("permission", ...)` rather than
                  letting the SQLite trigger raise an OperationalError.
    """
    if not _column_exists(conn, "learned_patterns", "trust_tier"):
        return False  # pre-v7 DB has no concept of protection
    row = conn.execute(
        "SELECT trust_tier FROM learned_patterns WHERE id = ?",
        (pattern_id,),
    ).fetchone()
    if row is None:
        return False
    return row[0] in PROTECTED_TRUST_TIERS


def _migrate_v8_validation_throttle(conn: sqlite3.Connection) -> None:
    """Migration v8 (Phase G.4): pattern_validations table for anti-sycophancy.

    PURPOSE:      Close audit finding A5 — agent self-validating the same
                  pattern repeatedly in one session silently inflated
                  confidence via the LTP formula. Throttle requires one
                  acceptance per (session_id, pattern_id) per window.
    INPUT:        sqlite3.Connection at schema v7.
    OUTPUT:       In-place upgrade to v8. No return value.
    DEPENDENCIES: learned_patterns.
    NOTES:        - Table is INSERT-only from the throttle path. We rely
                    on created_at + window arithmetic rather than UPDATE.
                  - No FK on pattern_id so a pattern delete doesn't raise;
                    orphaned rows are fine (they decay out of window).
                  - `was_throttled` column lets analytics separate
                    accepted validations from rejected ones for later
                    sycophancy-detection work (Phase G follow-up).
    """
    conn.executescript("""\
CREATE TABLE IF NOT EXISTS pattern_validations (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT NOT NULL,
    pattern_id     INTEGER NOT NULL,
    was_helpful    INTEGER NOT NULL,
    was_throttled  INTEGER NOT NULL DEFAULT 0,
    created_at     DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_pattern_validations_session_pattern
    ON pattern_validations(session_id, pattern_id);
CREATE INDEX IF NOT EXISTS idx_pattern_validations_created
    ON pattern_validations(created_at);
""")
    logger.info("Phase G.4 validation-throttle migration v8 applied: pattern_validations")


def has_pattern_validations_table(conn: sqlite3.Connection) -> bool:
    """Check whether the pattern_validations table exists (migration v8)."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='pattern_validations'"
    ).fetchone()
    return row is not None


def _migrate_v9_docs_fts(conn: sqlite3.Connection) -> None:
    """Migration v9 (Phase G.7.3): FTS5 virtual table over document_chunks.

    PURPOSE:      Lexical fallback for `cos_doc_search` when the query is an
                  exact identifier or when embeddings are unavailable.
    INPUT:        sqlite3.Connection at schema v8.
    OUTPUT:       In-place upgrade to v9. No return value.
    DEPENDENCIES: document_chunks (v5).
    NOTES:        - Graceful degradation — skips silently without FTS5.
                  - Triggers keep FTS in sync on INSERT/UPDATE/DELETE.
                  - Back-fill inserts existing rows.
    """
    if not has_fts5(conn):
        logger.warning(
            "FTS5 unavailable — skipping document_chunks_fts. doc_search "
            "lexical fallback will degrade to LIKE."
        )
        return

    conn.executescript("""\
CREATE VIRTUAL TABLE IF NOT EXISTS document_chunks_fts USING fts5(
    heading_path, content,
    content='document_chunks', content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS document_chunks_ai AFTER INSERT ON document_chunks BEGIN
    INSERT INTO document_chunks_fts(rowid, heading_path, content)
    VALUES (new.id, new.heading_path, new.content);
END;

CREATE TRIGGER IF NOT EXISTS document_chunks_au AFTER UPDATE ON document_chunks BEGIN
    INSERT INTO document_chunks_fts(document_chunks_fts, rowid, heading_path, content)
    VALUES ('delete', old.id, old.heading_path, old.content);
    INSERT INTO document_chunks_fts(rowid, heading_path, content)
    VALUES (new.id, new.heading_path, new.content);
END;

CREATE TRIGGER IF NOT EXISTS document_chunks_ad AFTER DELETE ON document_chunks BEGIN
    INSERT INTO document_chunks_fts(document_chunks_fts, rowid, heading_path, content)
    VALUES ('delete', old.id, old.heading_path, old.content);
END;
""")

    conn.execute(
        "INSERT INTO document_chunks_fts(rowid, heading_path, content) "
        "SELECT id, heading_path, content FROM document_chunks "
        "WHERE id NOT IN (SELECT rowid FROM document_chunks_fts)"
    )
    logger.info("Phase G.7.3 FTS5 docs migration v9 applied: document_chunks_fts")


def has_document_chunks_fts(conn: sqlite3.Connection) -> bool:
    """Check whether document_chunks_fts exists (v9 + FTS5 available)."""
    row = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='document_chunks_fts'"
    ).fetchone()
    return row is not None


def _migrate_v10_retrievals(conn: sqlite3.Connection) -> None:
    """Migration v10 (Phase G.8): retrievals table for outcome-driven priority.

    PURPOSE:      Log every chunk/pattern/task the agent retrieved so we can
                  later correlate retrievals with task outcomes and boost the
                  priority of chunks that led to success.
    INPUT:        sqlite3.Connection at schema v9.
    OUTPUT:       In-place upgrade to v10.
    DEPENDENCIES: document_chunks, learned_patterns, observations, tasks.
    NOTES:        - `outcome` is NULL at insert time; task-done back-fills it
                    based on the active task's result (success/rework/blocked).
                  - `was_cited` tracks whether the agent declared "I used this"
                    via `cos_retrieval_cite`. Priority learning only moves
                    chunks the agent actively cited — passive retrievals are
                    weaker signal.
                  - No FK — tables may move/rename; we resolve at read time.
    """
    conn.executescript("""\
CREATE TABLE IF NOT EXISTS retrievals (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT NOT NULL,
    task_id        TEXT,
    layer          TEXT NOT NULL,
    query          TEXT NOT NULL,
    source_table   TEXT NOT NULL,
    source_id      INTEGER NOT NULL,
    score          REAL,
    was_cited      INTEGER NOT NULL DEFAULT 0,
    outcome        TEXT,
    created_at     DATETIME DEFAULT CURRENT_TIMESTAMP,
    outcome_at     DATETIME
);

CREATE INDEX IF NOT EXISTS idx_retrievals_task      ON retrievals(task_id);
CREATE INDEX IF NOT EXISTS idx_retrievals_session   ON retrievals(session_id);
CREATE INDEX IF NOT EXISTS idx_retrievals_source    ON retrievals(source_table, source_id);
CREATE INDEX IF NOT EXISTS idx_retrievals_outcome   ON retrievals(outcome);
""")
    logger.info("Phase G.8 retrievals migration v10 applied")


def has_retrievals_table(conn: sqlite3.Connection) -> bool:
    """Check whether the retrievals table exists (migration v10)."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='retrievals'"
    ).fetchone()
    return row is not None


def _migrate_v11_retrieval_quality(conn: sqlite3.Connection) -> None:
    """Migration v11 (Phase G.11): retrieval precision tracking.

    PURPOSE:      Gate the eventual LLM contextual-chunk enrichment with a
                  measured precision metric. If we never see mean precision
                  dip below 0.7 over a healthy sample, we never pay the
                  cost of a per-chunk LLM pass.
    INPUT:        sqlite3.Connection at schema v10.
    OUTPUT:       Adds:
                    - retrieval_quality table (per-retrieval precision signal)
                    - contextual_chunks column on document_chunks
                      (nullable — populated only if enrichment enabled)
    DEPENDENCIES: retrievals (v10), document_chunks (v5).
    NOTES:        Column add is guarded by `_column_exists` so re-running
                  on a partially-migrated DB is safe.
    """
    conn.executescript("""\
CREATE TABLE IF NOT EXISTS retrieval_quality (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    retrieval_id    INTEGER NOT NULL,
    task_id         TEXT,
    layer           TEXT NOT NULL,
    query           TEXT,
    precision       REAL,
    signal_source   TEXT NOT NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_retrieval_quality_task
    ON retrieval_quality(task_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_quality_layer
    ON retrieval_quality(layer);
CREATE INDEX IF NOT EXISTS idx_retrieval_quality_created
    ON retrieval_quality(created_at);
""")

    # Contextual chunk text — LLM-generated situating sentence prepended at
    # embed time. Column is nullable until G.11 enrichment runs; retrieval
    # stays on the plain heading-path prefix meanwhile.
    if not _column_exists(conn, "document_chunks", "contextual_prefix"):
        conn.execute(
            "ALTER TABLE document_chunks ADD COLUMN contextual_prefix TEXT"
        )
    if not _column_exists(conn, "document_chunks", "context_model"):
        conn.execute(
            "ALTER TABLE document_chunks ADD COLUMN context_model TEXT"
        )
    logger.info(
        "Phase G.11 migration v11 applied: retrieval_quality + contextual chunk columns"
    )


def has_retrieval_quality_table(conn: sqlite3.Connection) -> bool:
    """Check whether the retrieval_quality table exists (migration v11)."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='retrieval_quality'"
    ).fetchone()
    return row is not None


def _migrate_v12_graph_os(conn: sqlite3.Connection) -> None:
    """Migration v12 (Phase I.0): graph_os knowledge-graph tables.

    PURPOSE:      Provision SQLite-backed storage for graph_os (sibling
                  subsystem to thinking_os). Adds graph_nodes,
                  graph_edges_v12, graph_evidence_v12, graph_nodes_fts
                  plus an embedding_dim column on legacy embeddings to
                  keep cosine_similarity correct during the MiniLM to
                  BGE-M3 migration window (see
                  docs/phase-i-knowledge-graph-plan.md Section 6 Stage 6).
    INPUT:        sqlite3.Connection at schema v11.
    OUTPUT:       Four tables created / column added. Idempotent.
    DEPENDENCIES: embeddings (v5) for the column add; has_fts5 for the
                  FTS virtual table.
    NOTES:        Append-only (Rule 10). Primary graph store is Kuzu
                  (Section 12); these SQLite tables are the fallback and
                  parity-test target in I.0 ship gate (Section 12.6).
    """
    conn.executescript("""\
CREATE TABLE IF NOT EXISTS graph_nodes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    kind          TEXT    NOT NULL,
    label         TEXT    NOT NULL,
    uid           TEXT    NOT NULL UNIQUE,
    file_path     TEXT,
    start_line    INTEGER,
    end_line      INTEGER,
    signature     TEXT,
    lang          TEXT,
    doc_blob      TEXT,
    ast_hash      TEXT,
    content_hash  TEXT,
    metadata_json TEXT DEFAULT '{}',
    created_at    INTEGER NOT NULL,
    updated_at    INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_kind_lang ON graph_nodes(kind, lang);
CREATE INDEX IF NOT EXISTS idx_graph_nodes_file      ON graph_nodes(file_path);

CREATE TABLE IF NOT EXISTS graph_edges_v12 (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id     INTEGER NOT NULL,
    target_id     INTEGER NOT NULL,
    edge_type     TEXT    NOT NULL,
    confidence    REAL    NOT NULL DEFAULT 1.0,
    extractor     TEXT    NOT NULL,
    source_span   TEXT,
    created_at    INTEGER NOT NULL,
    updated_at    INTEGER NOT NULL,
    UNIQUE(source_id, target_id, edge_type, extractor),
    FOREIGN KEY (source_id) REFERENCES graph_nodes(id) ON DELETE CASCADE,
    FOREIGN KEY (target_id) REFERENCES graph_nodes(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_graph_edges_source ON graph_edges_v12(source_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_graph_edges_target ON graph_edges_v12(target_id, edge_type);
CREATE INDEX IF NOT EXISTS idx_graph_edges_type   ON graph_edges_v12(edge_type);

CREATE TABLE IF NOT EXISTS graph_evidence_v12 (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    edge_id      INTEGER NOT NULL,
    signal_name  TEXT    NOT NULL,
    weight       REAL    NOT NULL,
    note         TEXT,
    created_at   INTEGER NOT NULL,
    FOREIGN KEY (edge_id) REFERENCES graph_edges_v12(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_graph_evidence_edge ON graph_evidence_v12(edge_id);
""")

    if has_fts5(conn):
        conn.executescript("""\
CREATE VIRTUAL TABLE IF NOT EXISTS graph_nodes_fts USING fts5(
    label, signature, doc_blob,
    content=graph_nodes,
    content_rowid=id,
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS graph_nodes_fts_ai AFTER INSERT ON graph_nodes BEGIN
    INSERT INTO graph_nodes_fts(rowid, label, signature, doc_blob)
      VALUES (new.id, new.label, COALESCE(new.signature, ''), COALESCE(new.doc_blob, ''));
END;
CREATE TRIGGER IF NOT EXISTS graph_nodes_fts_ad AFTER DELETE ON graph_nodes BEGIN
    INSERT INTO graph_nodes_fts(graph_nodes_fts, rowid, label, signature, doc_blob)
      VALUES ('delete', old.id, old.label, COALESCE(old.signature, ''), COALESCE(old.doc_blob, ''));
END;
CREATE TRIGGER IF NOT EXISTS graph_nodes_fts_au AFTER UPDATE ON graph_nodes BEGIN
    INSERT INTO graph_nodes_fts(graph_nodes_fts, rowid, label, signature, doc_blob)
      VALUES ('delete', old.id, old.label, COALESCE(old.signature, ''), COALESCE(old.doc_blob, ''));
    INSERT INTO graph_nodes_fts(rowid, label, signature, doc_blob)
      VALUES (new.id, new.label, COALESCE(new.signature, ''), COALESCE(new.doc_blob, ''));
END;
""")

    if has_embeddings_table(conn) and not _column_exists(conn, "embeddings", "embedding_dim"):
        conn.execute(
            "ALTER TABLE embeddings ADD COLUMN embedding_dim INTEGER DEFAULT 384"
        )

    logger.info(
        "Phase I.0 migration v12 applied: graph_nodes + graph_edges_v12 + "
        "graph_evidence_v12 + graph_nodes_fts; embeddings.embedding_dim added"
    )


def has_graph_nodes_table(conn: sqlite3.Connection) -> bool:
    """Check whether the graph_nodes table exists (migration v12)."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='graph_nodes'"
    ).fetchone()
    return row is not None


def has_graph_edges_table(conn: sqlite3.Connection) -> bool:
    """Check whether the graph_edges_v12 table exists (migration v12)."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='graph_edges_v12'"
    ).fetchone()
    return row is not None


def has_graph_evidence_table(conn: sqlite3.Connection) -> bool:
    """Check whether the graph_evidence_v12 table exists (migration v12)."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='graph_evidence_v12'"
    ).fetchone()
    return row is not None


def has_graph_nodes_fts(conn: sqlite3.Connection) -> bool:
    """Check whether the graph_nodes_fts virtual table exists (v12)."""
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='graph_nodes_fts'"
    ).fetchone()
    return row is not None


def _migrate_v13_board_os(conn: sqlite3.Connection) -> None:
    """Migration v13 (Phase L.0): board_os Scrumban task workflow extensions.

    PURPOSE:      Extend the existing `tasks` table (v6) with Scrumban
                  workflow state — swimlane, kind, epic, labels_json,
                  priority, appetite, started_at, completed_at,
                  agent_session, work_log_last_5 — and add a new
                  task_status_history audit table.  See
                  docs/phase-l-scrumban-task-system-plan.md §6.3.
    INPUT:        sqlite3.Connection at schema v12.
    OUTPUT:       Columns added to tasks (idempotent via _column_exists);
                  task_status_history table created; new indices.
    DEPENDENCIES: tasks table (migration v6).
    NOTES:        Append-only (Rule 10).  Existing rows survive — new
                  columns default to NULL (or '[]' for labels_json /
                  work_log_last_5).  Legacy status values (open / wip /
                  done) remain readable; the parser at
                  core/board_os/parser.py (ships in L.1) maps them on
                  read to the new 8-value enum (icebox / ready /
                  emergency / in_progress / testing / complete /
                  blocked / archive).
    """
    # Idempotent ADD COLUMN (re-running is safe).
    if not _column_exists(conn, "tasks", "swimlane"):
        conn.execute("ALTER TABLE tasks ADD COLUMN swimlane TEXT")
    if not _column_exists(conn, "tasks", "kind"):
        conn.execute("ALTER TABLE tasks ADD COLUMN kind TEXT")
    if not _column_exists(conn, "tasks", "epic"):
        conn.execute("ALTER TABLE tasks ADD COLUMN epic TEXT")
    if not _column_exists(conn, "tasks", "labels_json"):
        conn.execute("ALTER TABLE tasks ADD COLUMN labels_json TEXT DEFAULT '[]'")
    if not _column_exists(conn, "tasks", "priority"):
        conn.execute("ALTER TABLE tasks ADD COLUMN priority TEXT")
    if not _column_exists(conn, "tasks", "appetite"):
        conn.execute("ALTER TABLE tasks ADD COLUMN appetite TEXT")
    if not _column_exists(conn, "tasks", "started_at"):
        conn.execute("ALTER TABLE tasks ADD COLUMN started_at INTEGER")
    if not _column_exists(conn, "tasks", "completed_at"):
        conn.execute("ALTER TABLE tasks ADD COLUMN completed_at INTEGER")
    if not _column_exists(conn, "tasks", "agent_session"):
        conn.execute("ALTER TABLE tasks ADD COLUMN agent_session TEXT")
    if not _column_exists(conn, "tasks", "work_log_last_5"):
        conn.execute(
            "ALTER TABLE tasks ADD COLUMN work_log_last_5 TEXT DEFAULT '[]'"
        )

    conn.executescript("""\
CREATE TABLE IF NOT EXISTS task_status_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         TEXT    NOT NULL,
    old_status      TEXT    NOT NULL,
    new_status      TEXT    NOT NULL,
    agent_session   TEXT,
    reason          TEXT,
    transitioned_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tsh_task
    ON task_status_history(task_id, transitioned_at);
CREATE INDEX IF NOT EXISTS idx_tsh_session
    ON task_status_history(agent_session, transitioned_at)
    WHERE agent_session IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_tasks_swimlane_status
    ON tasks(swimlane, status);
CREATE INDEX IF NOT EXISTS idx_tasks_kind_status
    ON tasks(kind, status);
CREATE INDEX IF NOT EXISTS idx_tasks_epic
    ON tasks(epic) WHERE epic IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_tasks_priority_status
    ON tasks(priority, status)
    WHERE status IN ('ready', 'in_progress', 'emergency');
""")

    logger.info(
        "Phase L.0 migration v13 applied: tasks +swimlane/kind/epic/"
        "priority/appetite/started_at/completed_at/agent_session/"
        "labels_json/work_log_last_5; task_status_history table; "
        "5 new indices"
    )


def _migrate_v14_cognition(conn: sqlite3.Connection) -> None:
    """Migration v14 (Phase M): formula-agent supervisor cognition tables.

    PURPOSE:      Add 4 append-only tables for the formula-agent dispatch
                  loop: backtrack_events, persona_selections,
                  ambiguity_violations, formula_dispatches.
    INPUT:        sqlite3.Connection at schema v13.
    OUTPUT:       4 new tables + 4 indices.
    DEPENDENCIES: No dependency on prior tables.
    NOTES:        All rows are append-only (<1 KB/row × ~50 rows/session).
                  WAL already on. Rule 10: never edit past migrations.
    """
    conn.executescript("""\
CREATE TABLE IF NOT EXISTS backtrack_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    from_formula TEXT   NOT NULL,
    to_formula  TEXT    NOT NULL,
    reason      TEXT    NOT NULL,
    ts          TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_backtrack_session
    ON backtrack_events(session_id, ts);

CREATE TABLE IF NOT EXISTS persona_selections (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    task_marker TEXT,
    persona_id  TEXT    NOT NULL,
    confidence  REAL    NOT NULL,
    reason      TEXT,
    intensity   TEXT    NOT NULL,
    ts          TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_persona_session
    ON persona_selections(session_id);

CREATE TABLE IF NOT EXISTS ambiguity_violations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    formula_id  TEXT    NOT NULL,
    step_id     TEXT,
    criterion   TEXT    NOT NULL,
    detail      TEXT,
    ts          TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ambiguity_session
    ON ambiguity_violations(session_id);

CREATE TABLE IF NOT EXISTS formula_dispatches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    task_marker TEXT,
    persona_id  TEXT    NOT NULL,
    formula_id  TEXT    NOT NULL,
    input_hash  TEXT    NOT NULL,
    output_hash TEXT,
    latency_ms  INTEGER,
    status      TEXT    NOT NULL,
    ts          TEXT    NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_dispatches_session
    ON formula_dispatches(session_id, ts);
""")
    logger.info(
        "Phase M migration v14 applied: backtrack_events, persona_selections, "
        "ambiguity_violations, formula_dispatches + 4 indices"
    )


def _migrate_v15_graph_edges_confidence_check(conn: sqlite3.Connection) -> None:
    """Migration v15 (graph_os S1 / B17): CHECK (confidence BETWEEN 0 AND 1).

    PURPOSE:      Enforce the [0,1] confidence range at the DB layer, not
                  just in the Python dataclass. Defends against direct
                  SQL writers (tests, migrations, manual scripts) leaving
                  invalid rows behind.
    INPUT:        sqlite3.Connection at schema v14.
    OUTPUT:       Two triggers on graph_edges_v12 (INSERT + UPDATE) that
                  raise ABORT when confidence is outside [0,1] OR NULL.
    DEPENDENCIES: graph_edges_v12 (v12).
    NOTES:        SQLite cannot ``ALTER TABLE ADD CONSTRAINT``, so the
                  CHECK is implemented as a BEFORE INSERT / BEFORE UPDATE
                  trigger pair. Idempotent via IF NOT EXISTS. Rule 9:
                  append-only — this is a new migration number, never an
                  edit to past migrations.
    """
    conn.executescript("""\
CREATE TRIGGER IF NOT EXISTS graph_edges_v12_confidence_ins
BEFORE INSERT ON graph_edges_v12
FOR EACH ROW
WHEN NEW.confidence IS NULL
  OR NEW.confidence < 0.0
  OR NEW.confidence > 1.0
BEGIN
    SELECT RAISE(ABORT, 'graph_edges_v12.confidence must lie in [0,1]');
END;

CREATE TRIGGER IF NOT EXISTS graph_edges_v12_confidence_upd
BEFORE UPDATE OF confidence ON graph_edges_v12
FOR EACH ROW
WHEN NEW.confidence IS NULL
  OR NEW.confidence < 0.0
  OR NEW.confidence > 1.0
BEGIN
    SELECT RAISE(ABORT, 'graph_edges_v12.confidence must lie in [0,1]');
END;
""")
    logger.info(
        "Migration v15 applied: graph_edges_v12 confidence CHECK triggers"
    )


def _migrate_v16_normalize_graph_node_kinds(conn: sqlite3.Connection) -> None:
    """Migration v16 (graph_os S3): normalize graph_nodes.kind values.

    PURPOSE:      S3 introduces a ``NodeKind`` enum + ``normalize_kind``
                  helper in ``core/graph_os/types.py``. Legacy rows use
                  colon-prefixed strings like ``code:function`` or
                  ``doc:heading``; this migration rewrites them to the
                  canonical short form (``function`` / ``doc_heading``)
                  so the upcoming SPA tree-view can key on a single
                  vocabulary.
    INPUT:        sqlite3.Connection at schema v15.
    OUTPUT:       Row counts are surfaced via logger.info; the caller
                  observes them through ``run_migrations`` logs.
    DEPENDENCIES: graph_nodes (migration v12). No-op when the table
                  doesn't exist or is empty.
    NOTES:        Append-only per Rule 9 — this is a **data migration**,
                  not a schema change. Wrapped in a transaction (via
                  SQLite's implicit transaction around UPDATE). Idempo-
                  tent: re-running normalizes already-normalized kinds
                  to themselves.
    """
    row = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='graph_nodes'"
    ).fetchone()
    if row is None:
        logger.debug("Migration v16: graph_nodes table not present — skip")
        return

    # Resolve ``normalize_kind`` via a sys.path-side-door so this
    # migration works both under the MCP server (which already has
    # ``core/`` on sys.path) and under test fixtures that only
    # pre-register ``core/thinking_os``.
    try:
        import sys as _sys
        from pathlib import Path as _Path
        core_dir = _Path(__file__).resolve().parent.parent
        core_str = str(core_dir)
        if core_str not in _sys.path:
            _sys.path.insert(0, core_str)
        from graph_os.types import normalize_kind as _normalize  # type: ignore
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Migration v16 could not import normalize_kind (%s) — "
            "skipping normalization; rows remain in legacy form",
            exc,
        )
        return

    rows = conn.execute(
        "SELECT DISTINCT kind FROM graph_nodes"
    ).fetchall()
    rename_map: dict[str, str] = {}
    for r in rows:
        legacy = r[0]
        if legacy is None:
            continue
        try:
            canonical = _normalize(legacy).value
        except ValueError:
            # Unknown kind — leave as-is so we don't silently drop data.
            continue
        if canonical != legacy:
            rename_map[legacy] = canonical

    total_updated = 0
    for legacy, canonical in rename_map.items():
        cur = conn.execute(
            "UPDATE graph_nodes SET kind = ? WHERE kind = ?",
            (canonical, legacy),
        )
        total_updated += cur.rowcount or 0
    conn.commit()
    logger.info(
        "Migration v16 applied: graph_nodes.kind normalized "
        "(%d kind(s) rewritten, %d row(s) updated)",
        len(rename_map),
        total_updated,
    )


def _migrate_v17_file_index_state(conn: sqlite3.Connection) -> None:
    """Migration v17 (graph_os V1): per-file content-hash cache.

    PURPOSE:      V1 introduces file-level incremental indexing. The
                  reindex_dispatch entry looks up the prior content
                  hash + extractor chain for a file; on a match it
                  skips the extractor pipeline entirely. This migration
                  creates the ``file_index_state`` table that backs
                  that cache.
    INPUT:        sqlite3.Connection at schema v16.
    OUTPUT:       ``file_index_state`` table + hash index created.
    DEPENDENCIES: none (self-contained).
    NOTES:        Append-only per Rule 9. Primary key is ``file_path``
                  so callers get one row per file, keyed by repo-relative
                  path. ``extractor_chain`` stores the comma-joined
                  chain (e.g. ``code_python,contracts``) so that a
                  different chain for the same file correctly forces a
                  reindex rather than a false cache hit.
    """
    conn.executescript(
        """
CREATE TABLE IF NOT EXISTS file_index_state (
    file_path           TEXT NOT NULL,
    content_hash        TEXT NOT NULL,
    extractor_chain     TEXT NOT NULL,
    nodes_written       INTEGER NOT NULL,
    edges_written       INTEGER NOT NULL,
    parse_errors_count  INTEGER NOT NULL DEFAULT 0,
    last_indexed_at     INTEGER NOT NULL,
    last_error          TEXT,
    PRIMARY KEY (file_path, extractor_chain)
);
CREATE INDEX IF NOT EXISTS idx_file_index_state_hash
    ON file_index_state(content_hash);
"""
    )
    conn.commit()
    logger.info(
        "Migration v17 applied: file_index_state table + hash index"
    )


def _migrate_v18_retrieval_router_log(conn: sqlite3.Connection) -> None:
    """Migration v18 (Phase J.3): retrieval_router_log append-only table."""
    conn.executescript(
        """
CREATE TABLE IF NOT EXISTS retrieval_router_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    query_hash      TEXT NOT NULL,
    query_shape     TEXT NOT NULL,
    confidence      REAL NOT NULL,
    chosen_layer    TEXT,
    fanout_layers   TEXT,
    bytes_returned  INTEGER,
    truncated       INTEGER DEFAULT 0,
    agent_override  TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_router_log_created
    ON retrieval_router_log(created_at);
CREATE INDEX IF NOT EXISTS idx_router_log_shape
    ON retrieval_router_log(query_shape);
"""
    )
    conn.commit()
    logger.info("Migration v18 applied: retrieval_router_log table + indexes")


def _migrate_v19_drop_ready_status(conn: sqlite3.Connection) -> None:
    """Migration v19: fold 'ready' status into icebox + 'ready' label.

    PURPOSE: Board-os dropped the dedicated 'ready' column (see
             core/board_os/config.py::STATUS_ENUM).  Any existing row
             with status='ready' must move to 'icebox' AND gain a
             'ready' label so the signal "this task is ready to pick up"
             survives the column collapse.
    NOTES:   Idempotent — re-running on a migrated DB finds no rows to
             rewrite and is a no-op.  Writes to task_status_history so
             the stream attribution shows WHY the task moved (reason =
             'migrated from ready column').
    """
    rows = conn.execute(
        "SELECT task_id, labels_json FROM tasks WHERE status = 'ready'",
    ).fetchall()

    if not rows:
        logger.info("Migration v19 applied: no 'ready' rows to migrate (clean DB)")
        return

    import json as _json
    import time as _time
    now_epoch = int(_time.time())

    for task_id, labels_json in rows:
        try:
            labels = _json.loads(labels_json) if labels_json else []
            if not isinstance(labels, list):
                labels = []
        except (TypeError, ValueError):
            labels = []
        if "ready" not in labels:
            labels.append("ready")
        conn.execute(
            "UPDATE tasks SET status = 'icebox', labels_json = ? WHERE task_id = ?",
            (_json.dumps(labels, ensure_ascii=False), task_id),
        )
        conn.execute(
            """
            INSERT INTO task_status_history
                (task_id, old_status, new_status, agent_session,
                 reason, transitioned_at)
            VALUES (?, 'ready', 'icebox', NULL, ?, ?)
            """,
            (task_id, "migrated from ready column (v19)", now_epoch),
        )
    conn.commit()
    logger.info(
        "Migration v19 applied: folded %d 'ready' task(s) into icebox + label",
        len(rows),
    )


def _column_exists_table(
    conn: sqlite3.Connection, table: str, column: str
) -> bool:
    """Local helper — pragma table_info reads. Defined inline to keep
    the migration self-contained (the file already has _column_exists
    earlier; this is only used by v20)."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def _migrate_v20_override_audit(conn: sqlite3.Connection) -> None:
    """Migration v20 — override audit columns on task_status_history.

    PURPOSE: Phase L.10 transition gates (see docs/phase-l10-plan.md).
             Every COS_*_OVERRIDE=1 must carry a reason. The reason and
             actor land in two new columns so retro/audit queries can
             enumerate bypassed gates without grepping logs.
    INPUT:   sqlite connection.
    OUTPUT:  task_status_history gains override_reason TEXT, override_actor
             TEXT, both NULL-default. Existing rows backfill to NULL.
    NOTES:   Idempotent — checks _column_exists_table before adding.
             ALTER TABLE ADD COLUMN with a NULL default is metadata-only
             on SQLite, so this is fast even on tables with millions of
             rows.
    """
    if not has_task_status_history_table(conn):
        # Older DBs that never reached v13 don't have this table; the
        # v13 migration will create it with the modern shape via
        # _migrate_v13_board_os, but if a future re-run order is shuffled
        # we should be defensive.
        logger.info(
            "Migration v20 skipped: task_status_history not present yet "
            "(v13 will create it; v20 re-runs once v13 lands)"
        )
        return

    if not _column_exists_table(conn, "task_status_history", "override_reason"):
        conn.execute(
            "ALTER TABLE task_status_history ADD COLUMN override_reason TEXT"
        )
    if not _column_exists_table(conn, "task_status_history", "override_actor"):
        conn.execute(
            "ALTER TABLE task_status_history ADD COLUMN override_actor TEXT"
        )

    # Index lets retro/audit queries scan only override rows efficiently.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_tsh_override "
        "ON task_status_history(override_reason) "
        "WHERE override_reason IS NOT NULL"
    )
    conn.commit()
    logger.info("Migration v20 applied: override audit columns on task_status_history")


def _migrate_v21_doc_audit_trail(conn: sqlite3.Connection) -> None:
    """Migration v21 — append-only doc edit + decision-history log.

    PURPOSE: Capture every documentation change so a human or agent can
             audit *what* was decided, *when* it changed, and *why*. Closes
             the audit gap noted in the Phase O retrieval review: outcomes
             have outcome_history; tasks have task_status_history; docs
             had nothing until now.
    INPUT:   sqlite connection.
    OUTPUT:  doc_audit_trail table + append-only triggers blocking
             UPDATE / DELETE on existing rows. Index on (doc_path, created_at)
             for fast per-doc timelines.
    NOTES:   Triggers mirror the pattern used for memory_audit. Reverts are
             modeled as a new row with action='reverted' + supersedes_id
             pointing at the decision being undone — never as a row
             rewrite. The hub UI surfaces the timeline via
             cos_audit_log MCP tool.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS doc_audit_trail (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_path          TEXT NOT NULL,
            session_id        TEXT,
            agent             TEXT,
            action            TEXT NOT NULL CHECK (action IN (
                'created','updated','deleted','reverted','moved','renamed'
            )),
            old_frontmatter   TEXT,
            new_frontmatter   TEXT,
            old_content_hash  TEXT,
            new_content_hash  TEXT,
            reason            TEXT,
            supersedes_id     INTEGER REFERENCES doc_audit_trail(id),
            created_at        DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_doc_audit_path_created
            ON doc_audit_trail(doc_path, created_at DESC);

        CREATE INDEX IF NOT EXISTS idx_doc_audit_session
            ON doc_audit_trail(session_id);

        CREATE INDEX IF NOT EXISTS idx_doc_audit_supersedes
            ON doc_audit_trail(supersedes_id)
            WHERE supersedes_id IS NOT NULL;

        -- Append-only: forbid UPDATE / DELETE on this table. The audit
        -- log is meaningful only if it cannot be rewritten.
        CREATE TRIGGER IF NOT EXISTS doc_audit_trail_no_update
        BEFORE UPDATE ON doc_audit_trail
        BEGIN
            SELECT RAISE(FAIL, 'doc_audit_trail is append-only');
        END;

        CREATE TRIGGER IF NOT EXISTS doc_audit_trail_no_delete
        BEFORE DELETE ON doc_audit_trail
        BEGIN
            SELECT RAISE(FAIL, 'doc_audit_trail is append-only');
        END;
        """
    )
    conn.commit()
    logger.info("Migration v21 applied: doc_audit_trail (append-only)")


def has_doc_audit_trail_table(conn: sqlite3.Connection) -> bool:
    """Check whether doc_audit_trail exists (migration v21)."""
    row = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='doc_audit_trail'"
    ).fetchone()
    return row is not None


def _migrate_v22_doc_chunks_metadata(conn: sqlite3.Connection) -> None:
    """Migration v22 — frontmatter metadata columns on document_chunks.

    PURPOSE: Enable Stage-1 metadata pre-filtering on cos_doc_search.
             Doc indexer was previously stripping the
             `<!-- domain:X | layer:Y | ssot:Z | updated:DATE -->` header
             before chunking, which discarded the very metadata RAG needs
             to enforce reality (correct era, correct domain, not
             superseded). Columns added:
               - domain      (BACKEND|FRONTEND|OPS|DOCS|...)
               - layer       (adr|playbook|spec|policy|reference|...)
               - ssot        (true|ref|false)
               - updated_iso (YYYY-MM-DD from frontmatter)
               - is_active   (1=live, 0=superseded — flipped via
                              cos_audit_log_record action='deleted'/'reverted')
    INPUT:   sqlite connection.
    OUTPUT:  Five columns + four indexes added; existing rows backfill to
             NULL/1 (default). doc_indexer.reindex() repopulates them.
    NOTES:   Idempotent — guards each ALTER on _column_exists_table.
             Indexes are partial where possible to keep storage minimal
             (most rows lack frontmatter on first migration; partial
             indexes skip those nulls).
    """
    if not _table_exists(conn, "document_chunks"):
        logger.info("Migration v22 skipped: document_chunks not present yet")
        return

    cols = [
        ("domain",      "TEXT"),
        ("layer",       "TEXT"),
        ("ssot",        "TEXT"),
        ("updated_iso", "TEXT"),
        ("is_active",   "INTEGER DEFAULT 1"),
    ]
    for name, decl in cols:
        if not _column_exists_table(conn, "document_chunks", name):
            conn.execute(f"ALTER TABLE document_chunks ADD COLUMN {name} {decl}")

    # Backfill is_active for rows that pre-date this migration.
    conn.execute(
        "UPDATE document_chunks SET is_active = 1 WHERE is_active IS NULL"
    )

    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_chunks_domain
            ON document_chunks(domain) WHERE domain IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_chunks_layer
            ON document_chunks(layer) WHERE layer IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_chunks_active
            ON document_chunks(is_active);
        CREATE INDEX IF NOT EXISTS idx_chunks_updated
            ON document_chunks(updated_iso) WHERE updated_iso IS NOT NULL;
        """
    )
    conn.commit()
    logger.info(
        "Migration v22 applied: document_chunks gained domain/layer/ssot/updated_iso/is_active"
    )


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def has_file_index_state_table(conn: sqlite3.Connection) -> bool:
    """Check whether the file_index_state table exists (migration v17)."""
    row = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='file_index_state'"
    ).fetchone()
    return row is not None


def has_formula_dispatches_table(conn: sqlite3.Connection) -> bool:
    """Check whether formula_dispatches exists (migration v14)."""
    row = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='formula_dispatches'"
    ).fetchone()
    return row is not None


def has_backtrack_events_table(conn: sqlite3.Connection) -> bool:
    """Check whether backtrack_events exists (migration v14)."""
    row = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='backtrack_events'"
    ).fetchone()
    return row is not None


def has_persona_selections_table(conn: sqlite3.Connection) -> bool:
    """Check whether persona_selections exists (migration v14)."""
    row = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='persona_selections'"
    ).fetchone()
    return row is not None


def has_task_status_history_table(conn: sqlite3.Connection) -> bool:
    """Check whether task_status_history exists (migration v13)."""
    row = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='task_status_history'"
    ).fetchone()
    return row is not None


def has_tasks_v13_columns(conn: sqlite3.Connection) -> bool:
    """Quick check whether the v13 columns are on the tasks table."""
    return _column_exists(conn, "tasks", "swimlane") and _column_exists(
        conn, "tasks", "kind"
    )


def record_audit(
    conn: sqlite3.Connection,
    *,
    actor: str,
    action: str,
    source_table: str,
    source_id: int | None = None,
    old_value: str | None = None,
    new_value: str | None = None,
    reason: str | None = None,
) -> int | None:
    """Append a row to memory_audit. Fire-and-forget — never raises.

    PURPOSE:      Single-chokepoint helper so every guard-emission looks
                  identical in the audit log.
    INPUT:        typed kwargs mirroring memory_audit columns.
    OUTPUT:       inserted rowid, or None if table missing (pre-v7).
    DEPENDENCIES: memory_audit table (v7+).
    NOTES:        Swallows OperationalError so callers can use this even
                  against pre-v7 DBs without branching.
    """
    if not has_memory_audit_table(conn):
        return None
    try:
        cursor = conn.execute(
            "INSERT INTO memory_audit "
            "(actor, action, source_table, source_id, old_value, new_value, reason) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (actor, action, source_table, source_id, old_value, new_value, reason),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.OperationalError as exc:
        logger.debug("record_audit skipped: %s", exc)
        return None


MIGRATIONS: list[tuple[int, str, MigrationAction]] = [
    (
        1,
        "TASK-141: initial schema — task_outcomes, agent_metrics, learned_patterns, experiment_log, observations, session_summaries",
        """\
-- task_outcomes: one row per completed task
CREATE TABLE IF NOT EXISTS task_outcomes (
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

-- agent_metrics: per-agent-invocation telemetry
CREATE TABLE IF NOT EXISTS agent_metrics (
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

-- learned_patterns: extracted reusable patterns with confidence
CREATE TABLE IF NOT EXISTS learned_patterns (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern         TEXT NOT NULL,
    memory_type     TEXT DEFAULT 'pattern',
    domain          TEXT,
    source          TEXT,
    confidence      REAL DEFAULT 0.5,
    decay_rate      REAL DEFAULT 0.1,
    impact_score    REAL DEFAULT 0.5,
    concepts        TEXT,
    times_validated INTEGER DEFAULT 0,
    times_violated  INTEGER DEFAULT 0,
    access_count    INTEGER DEFAULT 0,
    last_accessed_at DATETIME,
    promoted_to     TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_validated  DATETIME
);

-- experiment_log: hypothesis tracking per task
CREATE TABLE IF NOT EXISTS experiment_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         TEXT,
    hypothesis      TEXT NOT NULL,
    test_description TEXT,
    outcome         TEXT,
    learning        TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- observations: raw captured observations from tool use
CREATE TABLE IF NOT EXISTS observations (
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

-- session_summaries: end-of-session digests.
--
-- Writer matrix (2026-04):
--   session_id, task_id, previous_session_id, files_touched,
--   observations_count, breakthrough_ids, duration_minutes
--       → filled by session_summary.build_session_summary on Stop hook.
--   request, learned
--       → filled by session_enrich.py from tool/outcome signal.
--   investigated, completed, next_steps
--       → RESERVED for narrative fields the agent populates via
--         cos_learn_narrative on breakthrough + a future explicit
--         retro tool. Nullable by design; NULL is not a bug.
CREATE TABLE IF NOT EXISTS session_summaries (
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
""",
    ),
    # TASK-152: FTS5 full-text search layer (callable migration — needs runtime FTS5 check)
    (2, "TASK-152: FTS5 observations_fts virtual table + INSERT/UPDATE/DELETE triggers", _migrate_v2_fts5),
    # TASK-148: routing_weights table for adaptive model/skill routing
    (3, "TASK-148: routing_weights table for adaptive routing",
     """\
CREATE TABLE IF NOT EXISTS routing_weights (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    domain          TEXT NOT NULL,
    complexity      TEXT NOT NULL,
    model           TEXT,
    skill           TEXT,
    success_rate    REAL DEFAULT 0.0,
    sample_count    INTEGER DEFAULT 0,
    last_updated    DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(domain, complexity, model, skill)
);
"""),
    # Brain features: outcome_history, concept_graph, session_summaries enrichment
    (4, "Brain features: outcome_history, concept_graph, session_summaries enrichment",
     _migrate_v4_brain_features),
    # Phase B: embeddings + document_chunks for RAG vector search
    (5, "Phase B RAG: embeddings + document_chunks tables",
     _migrate_v5_rag),
    # Phase C: tasks table for hybrid task store
    (6, "Phase C task store: tasks table indexing docs/tasks/*.md",
     _migrate_v6_tasks),
    # Phase G.1: brain hardening — trust_tier, provenance, memory_audit
    (7, "Phase G.1 brain hardening: trust_tier + provenance + memory_audit",
     _migrate_v7_brain_hardening),
    # Phase G.4: self-validation throttle
    (8, "Phase G.4 validation throttle: pattern_validations table",
     _migrate_v8_validation_throttle),
    # Phase G.7.3: FTS5 over document_chunks for lexical doc fallback
    (9, "Phase G.7.3 docs FTS: document_chunks_fts + triggers",
     _migrate_v9_docs_fts),
    # Phase G.8: retrievals table — audit + feedback loop
    (10, "Phase G.8 retrieval-outcome loop: retrievals table",
     _migrate_v10_retrievals),
    # Phase G.11: retrieval quality tracker + contextual-chunk scaffolding
    (11, "Phase G.11 retrieval quality: retrieval_quality + contextual chunk columns",
     _migrate_v11_retrieval_quality),
    # Phase I.0: graph_os knowledge-graph tables + embedding_dim column
    (12, "Phase I.0 graph_os: graph_nodes + graph_edges_v12 + graph_evidence_v12 + graph_nodes_fts + embeddings.embedding_dim",
     _migrate_v12_graph_os),
    # Phase L.0: board_os Scrumban — extend tasks + task_status_history
    (13, "Phase L.0 board_os: tasks +swimlane/kind/epic/priority/appetite/started_at/completed_at/agent_session/labels_json/work_log_last_5; task_status_history",
     _migrate_v13_board_os),
    # Phase M: formula-agent supervisor — 4 cognition tables
    (14, "Phase M formula-agents: backtrack_events + persona_selections + ambiguity_violations + formula_dispatches",
     _migrate_v14_cognition),
    # graph_os S1 / B17: CHECK(confidence BETWEEN 0 AND 1) triggers on graph_edges_v12
    (15, "graph_os S1 B17: graph_edges_v12 confidence CHECK triggers (INSERT + UPDATE)",
     _migrate_v15_graph_edges_confidence_check),
    # graph_os S3: data migration — normalize graph_nodes.kind legacy values
    (16, "graph_os S3: normalize graph_nodes.kind via NodeKind/normalize_kind",
     _migrate_v16_normalize_graph_node_kinds),
    # graph_os V1: file-level incremental indexing — file_index_state cache
    (17, "graph_os V1: file_index_state cache table for incremental reindex",
     _migrate_v17_file_index_state),
    # Phase J.3: retrieval router telemetry table
    (18, "Phase J.3 retrieval router telemetry: retrieval_router_log table",
     _migrate_v18_retrieval_router_log),
    # Phase ?.board: drop 'ready' column — fold into icebox + 'ready' label
    (19, "board_os: drop 'ready' status, migrate existing rows to icebox + 'ready' label",
     _migrate_v19_drop_ready_status),
    # Phase L.10: override audit — task_status_history.override_reason/actor
    (20, "Phase L.10: override audit columns on task_status_history",
     _migrate_v20_override_audit),
    # Phase O: doc_audit_trail — append-only doc edit + decision history
    (21, "Phase O: doc_audit_trail (append-only) for doc edits + decision history",
     _migrate_v21_doc_audit_trail),
    # Phase O: document_chunks frontmatter metadata for Stage-1 RAG pre-filter
    (22, "Phase O: document_chunks frontmatter metadata (domain/layer/ssot/updated_iso/is_active)",
     _migrate_v22_doc_chunks_metadata),
]


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _apply_pragmas(conn: sqlite3.Connection) -> None:
    """Apply performance and safety PRAGMAs."""
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA temp_store = MEMORY")
    conn.execute("PRAGMA cache_size = -64000")  # 64 MB


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a connection with WAL mode and safety PRAGMAs.

    Args:
        db_path: Path to the SQLite database file.
                 Defaults to .coding-os/thinking_os.db (via COS_DB_PATH env).

    Returns:
        A configured sqlite3.Connection.
    """
    path = str(db_path or DEFAULT_DB_PATH)
    # check_same_thread=False: single-writer model enforced by SqliteBackend's
    # RLock + WAL. Without this, any consumer that shares the connection
    # across threads (e.g. MCP server, web routes, test harness) hits
    # sqlite3.ProgrammingError. Matches get_pooled_conn above.
    conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _apply_pragmas(conn)
    return conn


# ---------------------------------------------------------------------------
# Phase N.5-A — Thread-local connection pool for multi-agent concurrency
# Spec: docs/phase-n-role-based-routing-plan.md §7a-A
# One cached connection per thread; WAL lets readers run concurrently;
# busy_timeout=5000 handles writer contention gracefully.
# ---------------------------------------------------------------------------

import threading  # noqa: E402

_thread_local = threading.local()
_pool_lock = threading.Lock()
_pool_stats = {"hits": 0, "misses": 0, "active": 0}


def get_pooled_conn(db_path: str | Path | None = None) -> sqlite3.Connection:
    """
    PURPOSE:      Thread-local cached SQLite connection for multi-agent load.
    INPUT:        db_path (defaults to DEFAULT_DB_PATH).
    OUTPUT:       sqlite3.Connection (WAL, busy_timeout=5000, reusable).
    DEPENDENCIES: threading.local, sqlite3.
    NOTES:        Do NOT .close() — the pool owns the lifecycle. Use
                  close_pool() at shutdown. Each thread gets its own
                  connection so per-call connect() overhead disappears.
    """
    path = str(db_path or DEFAULT_DB_PATH)
    existing = getattr(_thread_local, "conns", {}).get(path)
    if existing is not None:
        try:
            existing.execute("SELECT 1").fetchone()
            with _pool_lock:
                _pool_stats["hits"] += 1
            return existing
        except sqlite3.Error:
            pass  # Dead connection, reopen below

    conn = sqlite3.connect(path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    _apply_pragmas(conn)
    if not hasattr(_thread_local, "conns"):
        _thread_local.conns = {}
    _thread_local.conns[path] = conn
    with _pool_lock:
        _pool_stats["misses"] += 1
        _pool_stats["active"] += 1
    return conn


def close_pool() -> None:
    """Close all pooled connections for the current thread. Safe to call repeatedly."""
    conns = getattr(_thread_local, "conns", {})
    for conn in conns.values():
        try:
            conn.close()
        except sqlite3.Error:
            pass
    _thread_local.conns = {}
    with _pool_lock:
        _pool_stats["active"] = max(0, _pool_stats["active"] - len(conns))


def pool_stats() -> dict[str, int]:
    """Return pool stats snapshot for observability (N.5-B)."""
    with _pool_lock:
        return dict(_pool_stats)


@contextmanager
def db_connection(db_path: str | Path | None = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager that yields a connection and closes it on exit."""
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Schema versioning & migration
# ---------------------------------------------------------------------------

def _ensure_version_table(conn: sqlite3.Connection) -> None:
    """Create the schema_version table if it doesn't exist."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version ("
        "  version    INTEGER PRIMARY KEY,"
        "  description TEXT,"
        "  applied_at DATETIME DEFAULT CURRENT_TIMESTAMP"
        ")"
    )
    conn.commit()


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the highest applied migration version, or 0 if none."""
    _ensure_version_table(conn)
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return row[0] if row[0] is not None else 0


def run_migrations(conn: sqlite3.Connection) -> list[int]:
    """Apply any unapplied migrations in order.

    Concurrency-safe: takes an EXCLUSIVE transaction on the version
    table so two simultaneously-opening connections don't both try to
    apply the same migration and trip the UNIQUE constraint. Idempotent
    via INSERT OR IGNORE on the version row.

    Returns:
        List of migration versions that were applied.
    """
    _ensure_version_table(conn)
    applied: list[int] = []

    try:
        conn.execute("BEGIN IMMEDIATE")
    except sqlite3.OperationalError:
        # Another writer holds the lock — wait briefly and re-read; if
        # we're already at the target version, return without doing
        # anything. This is the common case under concurrent dispatcher
        # workers.
        pass
    try:
        current = get_schema_version(conn)
        for version, description, action in MIGRATIONS:
            if version <= current:
                continue
            logger.info("Applying migration v%d: %s", version, description)
            try:
                if callable(action):
                    action(conn)
                else:
                    conn.executescript(action)
            except sqlite3.OperationalError as exc:
                # ALTER TABLE under concurrent runners can race past the
                # column-exists guard — skip when the message explicitly
                # confirms the schema is already where we want it.
                if "duplicate column name" in str(exc).lower():
                    logger.debug(
                        "migration v%d ALTER race tolerated: %s", version, exc,
                    )
                else:
                    raise
            conn.execute(
                "INSERT OR IGNORE INTO schema_version (version, description) "
                "VALUES (?, ?)",
                (version, description),
            )
            applied.append(version)
        conn.commit()
    except sqlite3.IntegrityError as exc:
        logger.debug("migration race resolved: %s", exc)
        conn.rollback()
        applied = []

    if applied:
        logger.info("Migrations applied: %s (now at v%d)", applied, applied[-1])
    else:
        logger.debug("Schema up-to-date at v%d", current)

    return applied


# ---------------------------------------------------------------------------
# Stats helpers (used by health tool)
# ---------------------------------------------------------------------------

_TABLES = [
    "task_outcomes",
    "agent_metrics",
    "learned_patterns",
    "experiment_log",
    "observations",
    "session_summaries",
    "outcome_history",
    "concept_graph",
    "embeddings",
    "document_chunks",
    "tasks",
    "memory_audit",
    "pattern_validations",
    "retrievals",
    "retrieval_quality",
    "graph_nodes",
    "graph_edges_v12",
    "graph_evidence_v12",
    "file_index_state",
    "retrieval_router_log",
]


def get_db_stats(conn: sqlite3.Connection) -> dict:
    """Collect row counts per table and DB file size."""
    stats: dict = {"tables": {}}

    for table in _TABLES:
        try:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608 — table names are hardcoded
            stats["tables"][table] = row[0]
        except sqlite3.OperationalError:
            stats["tables"][table] = None  # table doesn't exist yet

    stats["schema_version"] = get_schema_version(conn)
    stats["fts5_available"] = has_fts5(conn)

    # File size
    db_path = conn.execute("PRAGMA database_list").fetchone()[2]
    if db_path and os.path.exists(db_path):
        stats["db_size_bytes"] = os.path.getsize(db_path)
    else:
        stats["db_size_bytes"] = 0

    return stats


# ---------------------------------------------------------------------------
# Bootstrap (called on server start and by --test)
# ---------------------------------------------------------------------------

def init_db(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open the DB, run migrations, return the live connection.

    Renames a legacy `thinking_os.db` sibling to the canonical
    `coding-os.db` once, before opening — silent no-op when the
    rename has already happened or no legacy file exists.
    """
    target = Path(db_path) if db_path else DEFAULT_DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    migrate_legacy_db_filename(target)
    conn = get_connection(str(target))
    run_migrations(conn)
    return conn
