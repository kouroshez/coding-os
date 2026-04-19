"""Tests for migration v12 (Phase I.0 — graph-os tables).

Ship gate from the roadmap (Section 19, I.0):
  - migration round-trip test
  - backend-parity matrix
  - determinism golden test

This module owns the round-trip + idempotency + schema shape checks.
Parity and determinism live in their own files.
"""

from __future__ import annotations

import pytest


def test_v12_creates_graph_tables(migrated_conn):
    import db  # type: ignore

    assert db.get_schema_version(migrated_conn) >= 12
    assert db.has_graph_nodes_table(migrated_conn)
    assert db.has_graph_edges_table(migrated_conn)
    assert db.has_graph_evidence_table(migrated_conn)


def test_v12_adds_embedding_dim_column(migrated_conn):
    import db  # type: ignore

    assert db.has_embeddings_table(migrated_conn)
    assert db._column_exists(migrated_conn, "embeddings", "embedding_dim")


def test_v12_is_idempotent(migrated_conn):
    import db  # type: ignore

    # Re-running migrations on an already-migrated DB should apply nothing.
    applied = db.run_migrations(migrated_conn)
    assert applied == []


def test_v12_fts_virtual_table_present_when_fts5_available(migrated_conn):
    import db  # type: ignore

    if db.has_fts5(migrated_conn):
        assert db.has_graph_nodes_fts(migrated_conn)


def test_v12_unique_edge_identity_enforced(migrated_conn):
    # Duplicate (source, target, edge_type, extractor) tuples must fail
    # at the DB layer — this is what makes upsert_edge safe to call twice.
    migrated_conn.execute(
        """
        INSERT INTO graph_nodes
          (kind, label, uid, created_at, updated_at)
        VALUES ('code:function', 'foo', 'code:function:foo', 0, 0)
        """
    )
    migrated_conn.execute(
        """
        INSERT INTO graph_nodes
          (kind, label, uid, created_at, updated_at)
        VALUES ('code:function', 'bar', 'code:function:bar', 0, 0)
        """
    )
    src_id = migrated_conn.execute(
        "SELECT id FROM graph_nodes WHERE uid='code:function:foo'"
    ).fetchone()[0]
    dst_id = migrated_conn.execute(
        "SELECT id FROM graph_nodes WHERE uid='code:function:bar'"
    ).fetchone()[0]

    migrated_conn.execute(
        """
        INSERT INTO graph_edges_v12
          (source_id, target_id, edge_type, extractor, created_at, updated_at)
        VALUES (?, ?, 'calls', 'test', 0, 0)
        """,
        (src_id, dst_id),
    )
    migrated_conn.commit()

    import sqlite3

    with pytest.raises(sqlite3.IntegrityError):
        migrated_conn.execute(
            """
            INSERT INTO graph_edges_v12
              (source_id, target_id, edge_type, extractor, created_at, updated_at)
            VALUES (?, ?, 'calls', 'test', 0, 0)
            """,
            (src_id, dst_id),
        )


def test_v12_foreign_key_cascade_removes_edges(migrated_conn):
    migrated_conn.execute("PRAGMA foreign_keys = ON")
    migrated_conn.execute(
        """
        INSERT INTO graph_nodes
          (kind, label, uid, created_at, updated_at)
        VALUES ('code:function', 'a', 'uid:a', 0, 0),
               ('code:function', 'b', 'uid:b', 0, 0)
        """
    )
    src = migrated_conn.execute("SELECT id FROM graph_nodes WHERE uid='uid:a'").fetchone()[0]
    dst = migrated_conn.execute("SELECT id FROM graph_nodes WHERE uid='uid:b'").fetchone()[0]
    migrated_conn.execute(
        """
        INSERT INTO graph_edges_v12
          (source_id, target_id, edge_type, extractor, created_at, updated_at)
        VALUES (?, ?, 'calls', 'test', 0, 0)
        """,
        (src, dst),
    )
    edge_id = migrated_conn.execute(
        "SELECT id FROM graph_edges_v12"
    ).fetchone()[0]
    migrated_conn.execute(
        """
        INSERT INTO graph_evidence_v12
          (edge_id, signal_name, weight, created_at)
        VALUES (?, 'same_scope', 0.5, 0)
        """,
        (edge_id,),
    )
    migrated_conn.commit()
    assert migrated_conn.execute("SELECT COUNT(*) FROM graph_evidence_v12").fetchone()[0] == 1

    migrated_conn.execute("DELETE FROM graph_nodes WHERE uid='uid:a'")
    migrated_conn.commit()

    # FK CASCADE removes the edge; and evidence cascades from the edge.
    assert migrated_conn.execute("SELECT COUNT(*) FROM graph_edges_v12").fetchone()[0] == 0
    assert migrated_conn.execute("SELECT COUNT(*) FROM graph_evidence_v12").fetchone()[0] == 0


def test_v12_stats_reports_new_tables(migrated_conn):
    import db  # type: ignore

    stats = db.get_db_stats(migrated_conn)
    assert "graph_nodes" in stats["tables"]
    assert "graph_edges_v12" in stats["tables"]
    assert "graph_evidence_v12" in stats["tables"]
    assert stats["schema_version"] >= 12
