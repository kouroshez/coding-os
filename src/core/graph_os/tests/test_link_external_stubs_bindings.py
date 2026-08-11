"""link_external_stubs: stub-edge rewriting to real cross-file targets."""

from __future__ import annotations

import sqlite3

from graph_os.backends.sqlite_backend import SqliteBackend
from graph_os.types import GraphNode


def _migrated_conn() -> sqlite3.Connection:
    import database as thinking_os_db

    conn = sqlite3.connect(":memory:")
    thinking_os_db.run_migrations(conn)
    return conn


def _import_node(file_path: str, name: str, module: str) -> GraphNode:
    return GraphNode(
        uid=f"code:import:{file_path}::{name}",
        kind="code:import",
        label=f"import {name}",
        file_path=file_path,
        metadata={
            "extractor": "code_python@v1",
            "imported": name,
            "source_module": module,
            "wildcard": False,
        },
    )


def test_import_binding_links_to_unique_symbol():
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)
    real = GraphNode(
        uid="code:function:src/core/thinking_os/database.py::init_db",
        kind="code:function",
        label="init_db",
        file_path="src/core/thinking_os/database.py",
    )
    importer = _import_node("src/cli/graph_commands.py", "init_db", "thinking_os.database")
    backend.bulk_upsert([real, importer], [])

    linked = backend.link_import_bindings()
    assert linked == 1
    row = conn.execute(
        "SELECT e.edge_type, e.extractor FROM graph_edges_v12 e "
        "JOIN graph_nodes s ON s.id=e.source_id AND s.uid=? "
        "JOIN graph_nodes t ON t.id=e.target_id AND t.uid=?",
        (importer.uid, real.uid),
    ).fetchone()
    assert row is not None
    assert row[0] == "imports"
    assert row[1] == "import_linker@v1"


def test_import_binding_resolves_path_hacked_alias():
    # `from database import init_db` (sys.path hack) — module suffix match.
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)
    real = GraphNode(
        uid="code:function:src/core/thinking_os/database.py::init_db",
        kind="code:function",
        label="init_db",
        file_path="src/core/thinking_os/database.py",
    )
    importer = _import_node("tests/test_cli.py", "init_db", "database")
    backend.bulk_upsert([real, importer], [])
    assert backend.link_import_bindings() == 1


def test_import_binding_skips_ambiguous_target():
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)
    real_a = GraphNode(
        uid="code:function:a/database.py::init_db",
        kind="code:function",
        label="init_db",
        file_path="a/database.py",
    )
    real_b = GraphNode(
        uid="code:function:b/database.py::init_db",
        kind="code:function",
        label="init_db",
        file_path="b/database.py",
    )
    importer = _import_node("x.py", "init_db", "database")
    backend.bulk_upsert([real_a, real_b, importer], [])
    assert backend.link_import_bindings() == 0


def test_import_binding_idempotent():
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)
    real = GraphNode(
        uid="code:function:pkg/mod.py::helper",
        kind="code:function",
        label="helper",
        file_path="pkg/mod.py",
    )
    importer = _import_node("app.py", "helper", "pkg.mod")
    backend.bulk_upsert([real, importer], [])
    assert backend.link_import_bindings() == 1
    assert backend.link_import_bindings() == 0


def test_import_binding_file_scoped():
    conn = _migrated_conn()
    backend = SqliteBackend(conn=conn)
    real = GraphNode(
        uid="code:function:pkg/mod.py::helper",
        kind="code:function",
        label="helper",
        file_path="pkg/mod.py",
    )
    in_scope = _import_node("app.py", "helper", "pkg.mod")
    out_of_scope = _import_node("other.py", "helper", "pkg.mod")
    backend.bulk_upsert([real, in_scope, out_of_scope], [])
    assert backend.link_import_bindings(file_path="app.py") == 1
