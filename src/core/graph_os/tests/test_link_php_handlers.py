"""link_php_handlers: Laravel controller-handler stubs → real method nodes (TASK-071)."""

from __future__ import annotations

import sqlite3

from graph_os.backends.sqlite_backend import SqliteBackend
from graph_os.types import GraphEdge, GraphNode


def _migrated_conn() -> sqlite3.Connection:
    import database as thinking_os_db

    conn = sqlite3.connect(":memory:")
    thinking_os_db.run_migrations(conn)
    return conn


def _setup(method_uids):
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)
    route = GraphNode(uid="cos:route:GET:/users", kind="cos:route", label="GET /users")
    stub = GraphNode(
        uid="code:external:phproute:UserController.index",
        kind="code:external",
        label="UserController.index",
    )
    nodes = [route, stub]
    for muid in method_uids:
        nodes.append(
            GraphNode(
                uid=muid,
                kind="code:method",
                label=muid.split(".")[-1],
                file_path=muid.split("::")[0][len("code:method:") :],
            )
        )
    edges = [
        GraphEdge(
            source_uid=route.uid,
            target_uid=stub.uid,
            edge_type="calls",
            extractor="contracts@v1",
            confidence=0.8,
        )
    ]
    backend.bulk_upsert(nodes, edges)
    return backend


def test_resolves_unique_controller_method():
    real = "code:method:app/Http/Controllers/UserController.php::UserController.index"
    backend = _setup([real])
    assert backend.link_php_handlers() == 1
    edges = list(backend.list_edges(edge_types=("calls",), limit=10))
    assert any(e.target_uid == real for e in edges)


def test_ambiguous_match_not_resolved():
    # Two UserController.index methods in different files → skip (never guess).
    a = "code:method:app/Http/Controllers/UserController.php::UserController.index"
    b = "code:method:packages/admin/UserController.php::UserController.index"
    backend = _setup([a, b])
    assert backend.link_php_handlers() == 0
    edges = list(backend.list_edges(edge_types=("calls",), limit=10))
    assert all(e.target_uid == "code:external:phproute:UserController.index" for e in edges)


def test_no_match_left_as_stub():
    backend = _setup([])  # no controller method node at all
    assert backend.link_php_handlers() == 0
