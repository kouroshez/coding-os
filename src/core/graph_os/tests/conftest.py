"""graph_os test fixtures.

Puts core/thinking_os on sys.path so tests can import the db module
directly (the MCP server does the same thing at runtime). Keeps tests
hermetic — every test gets a fresh SQLite file under a temp dir.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from graph_os.tools import graph
from graph_os.types import GraphEdge, GraphNode

_GRAPH_OS_DIR = Path(__file__).resolve().parent.parent
_THINKING_OS_DIR = _GRAPH_OS_DIR.parent / "thinking_os"

if str(_THINKING_OS_DIR) not in sys.path:
    sys.path.insert(0, str(_THINKING_OS_DIR))
if str(_GRAPH_OS_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_GRAPH_OS_DIR.parent))


@pytest.fixture()
def fresh_db_path(tmp_path: Path) -> str:
    """Return a fresh sqlite3 path inside tmp_path (no schema yet)."""
    return str(tmp_path / "graph_os-test.db")


@pytest.fixture()
def migrated_conn(fresh_db_path: str):
    """Return a freshly initialised sqlite3 connection at schema v12."""
    import database  # type: ignore

    conn = database.init_db(fresh_db_path)
    try:
        yield conn
    finally:
        conn.close()


@pytest.fixture()
def seeded_backend(migrated_conn, monkeypatch, tmp_path):
    """Seed the backend with a small fixture graph + wire the tools."""
    from graph_os.backends.sqlite_backend import SqliteBackend

    backend = SqliteBackend(conn=migrated_conn)
    # Force the tools module to use *this* backend.
    graph._BACKEND_SINGLETON = backend
    monkeypatch.setattr(graph, "_backend", lambda *, backend=None: graph._BACKEND_SINGLETON)

    nodes = [
        GraphNode(
            uid="code:function:a.py::foo",
            kind="code:function",
            label="foo",
            file_path="a.py",
            start_line=1,
        ),
        GraphNode(
            uid="code:function:a.py::bar",
            kind="code:function",
            label="bar",
            file_path="a.py",
            start_line=10,
        ),
        GraphNode(
            uid="code:function:a.py::baz",
            kind="code:function",
            label="baz_handler",
            file_path="a.py",
            start_line=20,
        ),
        GraphNode(uid="doc:file:docs/x.md", kind="doc:file", label="x.md", file_path="docs/x.md"),
        GraphNode(
            uid="cos:route:GET:/users",
            kind="cos:route",
            label="GET /users",
            file_path="app.py",
            metadata={"kind": "http", "method": "get", "path": "/users", "framework": "fastapi"},
        ),
        GraphNode(
            uid="cos:mcp_tool:cos_graph_query",
            kind="cos:mcp_tool",
            label="mcp:cos_graph_query",
            file_path="srv.py",
            metadata={"kind": "mcp", "method": "rpc", "path": "cos_graph_query"},
        ),
        GraphNode(uid="code:file:a.py", kind="code:file", label="a.py", file_path="a.py"),
        GraphNode(
            uid="code:class:a.py::Widget",
            kind="code:class",
            label="Widget",
            file_path="a.py",
            start_line=30,
        ),
        GraphNode(
            uid="code:function:a.py::make_widget",
            kind="code:function",
            label="make_widget",
            file_path="a.py",
            start_line=40,
        ),
        # F6 fixture: an external/unresolved node — must NOT dominate
        # centrality or PageRank when include_external defaults False.
        GraphNode(
            uid="code:external:unresolved:str",
            kind="identifier",
            label="unresolved:str",
            file_path=None,
        ),
    ]
    edges = [
        GraphEdge(
            source_uid="code:function:a.py::foo",
            target_uid="code:function:a.py::bar",
            edge_type="calls",
            extractor="test",
            confidence=0.9,
        ),
        GraphEdge(
            source_uid="code:function:a.py::bar",
            target_uid="code:function:a.py::baz",
            edge_type="calls",
            extractor="test",
            confidence=0.6,
        ),
        GraphEdge(
            source_uid="code:file:a.py",
            target_uid="code:function:a.py::foo",
            edge_type="contains",
            extractor="test",
            confidence=1.0,
        ),
        GraphEdge(
            source_uid="doc:file:docs/x.md",
            target_uid="code:function:a.py::foo",
            edge_type="references_doc",
            extractor="test",
            confidence=0.85,
        ),
        GraphEdge(
            source_uid="code:file:a.py",
            target_uid="cos:route:GET:/users",
            edge_type="handles_route",
            extractor="test",
            confidence=0.9,
        ),
        GraphEdge(
            source_uid="code:file:a.py",
            target_uid="cos:mcp_tool:cos_graph_query",
            edge_type="handles_tool",
            extractor="test",
            confidence=0.95,
        ),
        # Class-consumer edges — rename_plan must surface these (F2/#6).
        GraphEdge(
            source_uid="code:function:a.py::make_widget",
            target_uid="code:class:a.py::Widget",
            edge_type="constructs",
            extractor="test",
            confidence=0.85,
        ),
        GraphEdge(
            source_uid="code:function:a.py::foo",
            target_uid="code:class:a.py::Widget",
            edge_type="has_param_type",
            extractor="test",
            confidence=0.85,
        ),
        # F6 fixture: lots of inbound edges to the external stub so
        # that, without the filter, it'd dominate the ranking.
        GraphEdge(
            source_uid="code:function:a.py::foo",
            target_uid="code:external:unresolved:str",
            edge_type="has_return_type",
            extractor="test",
            confidence=0.7,
        ),
        GraphEdge(
            source_uid="code:function:a.py::bar",
            target_uid="code:external:unresolved:str",
            edge_type="has_return_type",
            extractor="test",
            confidence=0.7,
        ),
        GraphEdge(
            source_uid="code:function:a.py::baz",
            target_uid="code:external:unresolved:str",
            edge_type="has_return_type",
            extractor="test",
            confidence=0.7,
        ),
    ]
    backend.bulk_upsert(nodes, edges)
    yield backend
    graph._BACKEND_SINGLETON = None
