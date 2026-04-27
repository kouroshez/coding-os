"""link_external_stubs: stub-edge rewriting to real cross-file targets."""
from __future__ import annotations

import sqlite3

from graph_os.backends.sqlite_backend import SqliteBackend
from graph_os.types import GraphEdge, GraphNode


def _migrated_conn() -> sqlite3.Connection:
    import db as thinking_os_db
    conn = sqlite3.connect(":memory:")
    thinking_os_db.run_migrations(conn)
    return conn


def test_resolves_relative_import_to_real_symbol():
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)

    real = GraphNode(
        uid="code:function:core/graph_os/types.py::normalize_kind",
        kind="code:function",
        label="normalize_kind",
        file_path="core/graph_os/types.py",
    )
    caller_file = GraphNode(
        uid="code:file:core/graph_os/backends/sqlite_backend.py",
        kind="code:file",
        label="sqlite_backend.py",
        file_path="core/graph_os/backends/sqlite_backend.py",
    )
    stub = GraphNode(
        uid="code:external:graph_os.types:normalize_kind",
        kind="code:external",
        label="normalize_kind",
        metadata={"stub": True, "extractor": "code_python@v1"},
    )
    backend.bulk_upsert([real, caller_file, stub], [
        GraphEdge(
            source_uid=caller_file.uid,
            target_uid=stub.uid,
            edge_type="calls",
            extractor="code_python@v1",
            confidence=0.4,
        )
    ])

    rewrites = backend.link_external_stubs()
    assert rewrites == 1

    edges = list(backend.list_edges(edge_types=("calls",), limit=10))
    assert len(edges) == 1
    assert edges[0].target_uid == real.uid


def test_skips_unresolvable_stubs():
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)

    src_file = GraphNode(
        uid="code:file:foo.py",
        kind="code:file",
        label="foo.py",
        file_path="foo.py",
    )
    stub = GraphNode(
        uid="code:external:nonexistent.module:missing_fn",
        kind="code:external",
        label="missing_fn",
        metadata={"stub": True, "extractor": "code_python@v1"},
    )
    backend.bulk_upsert([src_file, stub], [
        GraphEdge(
            source_uid=src_file.uid,
            target_uid=stub.uid,
            edge_type="calls",
            extractor="code_python@v1",
            confidence=0.3,
        )
    ])

    rewrites = backend.link_external_stubs()
    assert rewrites == 0


def test_label_with_special_chars_does_not_match_unrelated():
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)

    other = GraphNode(
        uid="code:function:src/other.py::foo",
        kind="code:function",
        label="foo",
        file_path="src/other.py",
    )
    src_file = GraphNode(
        uid="code:file:src/caller.py",
        kind="code:file",
        label="caller.py",
        file_path="src/caller.py",
    )
    stub = GraphNode(
        uid="code:external:totally.unrelated:foo",
        kind="code:external",
        label="foo",
        metadata={"stub": True, "extractor": "code_python@v1"},
    )
    backend.bulk_upsert([other, src_file, stub], [
        GraphEdge(
            source_uid=src_file.uid,
            target_uid=stub.uid,
            edge_type="calls",
            extractor="code_python@v1",
            confidence=0.4,
        )
    ])

    rewrites = backend.link_external_stubs()
    assert rewrites == 0
