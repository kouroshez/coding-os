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


def test_from_package_import_submodule_binds_to_the_submodules_file(tmp_path, monkeypatch):
    import json

    from database import init_db  # type: ignore

    from graph_os.tools import graph as graph_tools
    from graph_os.tools.reindex_dispatch import dispatch

    files = {
        "app/__init__.py": "",
        "app/routers/__init__.py": "from .shared import status\n",
        "app/routers/shared.py": "def status():\n    return 1\n",
        "app/routers/triage.py": "def route():\n    return 1\n",
        "app/main.py": "from app.routers import status, triage\n\ntriage.route()\n",
        "app/jobs.py": "from .routers import triage\n",
    }
    (tmp_path / ".coding-os").mkdir()
    for relative, text in files.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    db = str(tmp_path / "graph.db")
    for relative in files:
        dispatch(tmp_path / relative, project_root=tmp_path, db_path=db, include_docs=False)
    test_backend = SqliteBackend(conn=init_db(db))
    test_backend.link_cross_file()
    monkeypatch.setattr(graph_tools, "_backend", lambda *, backend=None: test_backend)

    def importers(path: str) -> set[str]:
        data = json.loads(graph_tools.cos_graph_references(f"code:file:{path}"))["data"]
        return {test_backend.get_node(row["source_uid"]).file_path for row in data["references"]}

    assert importers("app/routers/triage.py") == {"app/main.py", "app/jobs.py"}
    assert "app/main.py" in importers("app/routers/shared.py")


def _module_node(dotted: str, file_path: str) -> GraphNode:
    return GraphNode(uid=f"code:module:{dotted}", kind="module", label=dotted, file_path=file_path)


def test_module_lookup_accepts_the_source_root_prefix_the_indexer_stripped():
    backend = SqliteBackend(conn=_migrated_conn())
    backend.bulk_upsert([_module_node("board_os.mcp_tools", "src/core/board_os/mcp_tools.py")], [])

    assert (
        backend._python_module_file("core.board_os.mcp_tools") == "src/core/board_os/mcp_tools.py"
    )
    assert backend._python_module_file("board_os.mcp_tools") == "src/core/board_os/mcp_tools.py"


def test_module_lookup_never_strips_onto_an_unrelated_local_module():
    backend = SqliteBackend(conn=_migrated_conn())
    backend.bulk_upsert([_module_node("db.models", "src/db/models.py")], [])

    assert backend._python_module_file("django.db.models") is None


def test_a_core_prefixed_call_through_a_facade_reaches_the_defining_function():
    # `from core.board_os import mcp_tools; mcp_tools.decode()` — mcp_tools
    # re-exports decode from _impl, and its module uid drops the `core.` root.
    backend = SqliteBackend(conn=_migrated_conn())
    real = GraphNode(
        uid="code:function:src/core/board_os/_impl.py::decode",
        kind="function",
        label="decode",
        file_path="src/core/board_os/_impl.py",
    )
    facade_import = _import_node("src/core/board_os/mcp_tools.py", "decode", "board_os._impl")
    caller = GraphNode(
        uid="code:function:tests/test_board.py::test_decode",
        kind="function",
        label="test_decode",
        file_path="tests/test_board.py",
        lang="py",
    )
    stub = GraphNode(
        uid="code:external:core.board_os.mcp_tools:decode",
        kind="external",
        label="decode",
    )
    backend.bulk_upsert(
        [
            real,
            facade_import,
            caller,
            stub,
            _module_node("board_os.mcp_tools", "src/core/board_os/mcp_tools.py"),
            _module_node("board_os._impl", "src/core/board_os/_impl.py"),
        ],
        [
            GraphEdge(
                source_uid=caller.uid,
                target_uid=stub.uid,
                edge_type="calls",
                extractor="code_python@v1",
            )
        ],
    )

    assert backend.link_external_stubs() == 1
    target = backend._conn.execute(
        "SELECT t.uid FROM graph_edges_v12 e JOIN graph_nodes s ON s.id = e.source_id "
        "JOIN graph_nodes t ON t.id = e.target_id WHERE s.uid = ? AND e.edge_type = 'calls'",
        (caller.uid,),
    ).fetchone()
    assert target == (real.uid,)
