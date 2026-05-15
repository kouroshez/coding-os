"""Regression: every migration creates the table it claims, no zombie schema."""

from __future__ import annotations

import sqlite3

import pytest

from database import init_db
from tools.retrieve import log_router_decision


# Tables every migration should leave behind. Update when adding a new
# migration. Order matters only for human readability here — the assertion
# walks the set.
_REQUIRED_TABLES = {
    "observations", "embeddings", "agent_metrics",
    "schema_version",
    # v7 brain hardening
    "memory_audit",
    # v10 retrievals
    "retrievals",
    # v11 outcomes
    "task_outcomes", "outcome_history",
    # v12 graph_os
    "graph_nodes", "graph_edges_v12", "graph_evidence_v12",
    # v13 board_os
    "tasks", "task_status_history",
    # v14 phase M
    "backtrack_events", "persona_selections",
    "ambiguity_violations", "formula_dispatches",
    # v17 reindex cache  ← THE BUG: was missing despite schema_version=v22
    "file_index_state",
    # v18 router telemetry
    "retrieval_router_log",
    # v19/20 board polish (no new tables)
    # v21 doc audit
    "doc_audit_trail",
    # v22 doc_chunks metadata cols (no new table — but document_chunks must exist)
    "document_chunks",
}


@pytest.fixture
def fresh_db(tmp_path):
    db_path = tmp_path / "audit.db"
    return init_db(str(db_path))


def test_every_migration_leaves_its_table(fresh_db: sqlite3.Connection) -> None:
    rows = fresh_db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    present = {r[0] for r in rows}
    missing = _REQUIRED_TABLES - present
    assert not missing, (
        f"Migration regression — schema_version advanced but tables missing: {missing}. "
        "If a migration intentionally dropped a table, remove it from _REQUIRED_TABLES."
    )


def test_schema_version_at_max(fresh_db: sqlite3.Connection) -> None:
    v = fresh_db.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    assert v >= 22, f"Expected schema_version >= 22, got {v}"


def test_router_log_writer_round_trip(fresh_db: sqlite3.Connection) -> None:
    """Zombie-table guard: retrieval_router_log gains rows from log_router_decision."""
    n_before = fresh_db.execute(
        "SELECT COUNT(*) FROM retrieval_router_log"
    ).fetchone()[0]
    rid = log_router_decision(
        fresh_db, query="cos_search()", chosen_layer="memory",
        bytes_returned=512,
    )
    assert rid is not None, "log_router_decision must return the inserted row id"
    n_after = fresh_db.execute(
        "SELECT COUNT(*) FROM retrieval_router_log"
    ).fetchone()[0]
    assert n_after == n_before + 1
    row = fresh_db.execute(
        "SELECT query_shape, chosen_layer FROM retrieval_router_log "
        "ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert row[0] == "identifier", f"expected shape=identifier, got {row[0]}"
    assert row[1] == "memory"


def test_router_log_classifies_query_shapes(fresh_db: sqlite3.Connection) -> None:
    cases = [
        ("snake_case_thing", "identifier"),
        ("CamelCaseThing", "identifier"),
        ("TASK-042", "task_id"),
        ("foo.py", "identifier"),
        ("how do I configure caching", "natural"),
        ("", "empty"),
    ]
    for query, expected in cases:
        log_router_decision(fresh_db, query=query, chosen_layer="docs")
        row = fresh_db.execute(
            "SELECT query_shape FROM retrieval_router_log "
            "ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert row[0] == expected, (
            f"query={query!r}: expected shape={expected}, got {row[0]}"
        )


def test_persona_selections_schema_accepts_writer_payload(fresh_db: sqlite3.Connection) -> None:
    """Lock the persona_selections columns the cognition writer relies on."""
    fresh_db.execute(
        "INSERT INTO persona_selections "
        "(session_id, task_marker, persona_id, confidence, reason, intensity) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("ses-test", "preset-foo", "researcher", 1.0, "preset", "default"),
    )
    fresh_db.commit()
    n = fresh_db.execute("SELECT COUNT(*) FROM persona_selections").fetchone()[0]
    assert n == 1
