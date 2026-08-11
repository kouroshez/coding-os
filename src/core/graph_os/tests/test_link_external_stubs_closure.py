"""link_external_stubs: stub-edge rewriting to real cross-file targets."""

from __future__ import annotations

import sqlite3

from graph_os.backends.sqlite_backend import SqliteBackend
from graph_os.types import GraphEdge, GraphNode


def _migrated_conn() -> sqlite3.Connection:
    import database as thinking_os_db

    conn = sqlite3.connect(":memory:")
    thinking_os_db.run_migrations(conn)
    return conn


def _spine_fixture(backend: SqliteBackend) -> None:
    nodes = [
        GraphNode(uid="folder:src", kind="folder", label="src", file_path="src"),
        GraphNode(uid="folder:src/core", kind="folder", label="core", file_path="src/core"),
        GraphNode(
            uid="code:file:src/core/a.py",
            kind="code:file",
            label="a.py",
            file_path="src/core/a.py",
        ),
        GraphNode(
            uid="code:function:src/core/a.py::f",
            kind="code:function",
            label="f",
            file_path="src/core/a.py",
        ),
        GraphNode(
            uid="doc:file:docs/x.md",
            kind="doc:file",
            label="x.md",
            file_path="docs/x.md",
        ),
        GraphNode(uid="folder:docs", kind="folder", label="docs", file_path="docs"),
    ]
    edges = [
        GraphEdge(
            source_uid="folder:src",
            target_uid="folder:src/core",
            edge_type="contains",
            extractor="t",
            confidence=1.0,
        ),
        GraphEdge(
            source_uid="folder:src/core",
            target_uid="code:file:src/core/a.py",
            edge_type="contains",
            extractor="t",
            confidence=1.0,
        ),
        GraphEdge(
            source_uid="code:file:src/core/a.py",
            target_uid="code:function:src/core/a.py::f",
            edge_type="contains",
            extractor="t",
            confidence=1.0,
        ),
        GraphEdge(
            source_uid="folder:docs",
            target_uid="doc:file:docs/x.md",
            edge_type="contains",
            extractor="t",
            confidence=1.0,
        ),
    ]
    backend.bulk_upsert(nodes, edges)


def test_bulk_closure_returns_full_ancestor_chain():
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)
    _spine_fixture(backend)
    ancestors, spine_edges = backend.contains_ancestors_bulk(["code:function:src/core/a.py::f"])
    ancestor_uids = {n.uid for n in ancestors}
    assert ancestor_uids == {"folder:src", "folder:src/core", "code:file:src/core/a.py"}
    pairs = {(e.source_uid, e.target_uid) for e in spine_edges}
    assert ("folder:src", "folder:src/core") in pairs
    assert ("code:file:src/core/a.py", "code:function:src/core/a.py::f") in pairs


def test_bulk_closure_multi_leaf_no_duplicates():
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)
    _spine_fixture(backend)
    ancestors, _ = backend.contains_ancestors_bulk(
        ["code:function:src/core/a.py::f", "code:file:src/core/a.py", "doc:file:docs/x.md"]
    )
    ancestor_uids = [n.uid for n in ancestors]
    assert len(ancestor_uids) == len(set(ancestor_uids))
    assert "folder:docs" in ancestor_uids
    # inputs are never echoed back as ancestors
    assert "doc:file:docs/x.md" not in ancestor_uids


def test_bulk_closure_empty_input():
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)
    assert backend.contains_ancestors_bulk([]) == ([], [])


def test_edges_among_returns_only_in_set_semantic_edges():
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)
    inside_a = GraphNode(
        uid="code:function:m.py::a", kind="code:function", label="a", file_path="m.py"
    )
    inside_b = GraphNode(
        uid="code:function:m.py::b", kind="code:function", label="b", file_path="m.py"
    )
    outside = GraphNode(
        uid="code:function:x.py::c", kind="code:function", label="c", file_path="x.py"
    )
    holder = GraphNode(uid="code:file:m.py", kind="code:file", label="m.py", file_path="m.py")
    backend.bulk_upsert(
        [inside_a, inside_b, outside, holder],
        [
            GraphEdge(
                source_uid=inside_a.uid,
                target_uid=inside_b.uid,
                edge_type="calls",
                extractor="t",
                confidence=0.9,
            ),
            GraphEdge(
                source_uid=inside_a.uid,
                target_uid=outside.uid,
                edge_type="calls",
                extractor="t",
                confidence=0.9,
            ),
            GraphEdge(
                source_uid=holder.uid,
                target_uid=inside_a.uid,
                edge_type="contains",
                extractor="t",
                confidence=1.0,
            ),
        ],
    )
    edges = backend.edges_among([inside_a.uid, inside_b.uid, holder.uid])
    pairs = {(e.source_uid, e.target_uid, e.edge_type) for e in edges}
    assert (inside_a.uid, inside_b.uid, "calls") in pairs
    assert all(e.target_uid != outside.uid for e in edges)
    assert all(e.edge_type != "contains" for e in edges)
