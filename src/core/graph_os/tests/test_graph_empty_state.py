"""Empty / sparse-graph handling for cos_graph_export + cos_graph_centrality (TASK-423).

A freshly-created or unindexed project has an empty graph. The Hub Graph tab
calls cos_graph_export(edge_types='contains'), and centrality may be called with
a `kind` filter. Before TASK-423 both validated the requested edge_type/kind
against `SELECT DISTINCT` over the (empty) DB, so a legitimate filter looked
like a typo and returned a hard fail ("unknown edge_type(s) ['contains'];
known: []"). The graph-os contract is "empty result is valid" — a valid filter
must return ok([]); only a genuine typo is a fail. These tests lock both halves
and guard the canonical edge-type set against drift.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from graph_os.tools import graph
from graph_os.types import GraphEdge, GraphNode


def _install(backend, monkeypatch) -> None:
    graph._BACKEND_SINGLETON = backend
    monkeypatch.setattr(graph, "_backend", lambda *, backend=None: graph._BACKEND_SINGLETON)


def _parse(value):
    # cos_graph_* tools serialize to a JSON string at the MCP boundary; decode.
    return json.loads(value) if isinstance(value, str) else value


@pytest.fixture()
def empty_backend(migrated_conn, monkeypatch):
    """A real, schema-v12 SQLite backend with ZERO nodes/edges (fresh project)."""
    from graph_os.backends.sqlite_backend import SqliteBackend

    backend = SqliteBackend(conn=migrated_conn)
    _install(backend, monkeypatch)
    try:
        yield backend
    finally:
        graph._BACKEND_SINGLETON = None


@pytest.fixture()
def contains_only_backend(migrated_conn, monkeypatch):
    """A SPARSE graph: only 'contains' edges (the docs-only fresh-project shape).

    Exercises the case a naive "skip validation when the DB is empty" fix would
    STILL get wrong — the DB is non-empty but a valid filter ('calls') matches
    zero rows, so present-rows validation would reject it.
    """
    from graph_os.backends.sqlite_backend import SqliteBackend

    backend = SqliteBackend(conn=migrated_conn)
    _install(backend, monkeypatch)
    nodes = [
        GraphNode(uid="code:file:a.py", kind="code:file", label="a.py", file_path="a.py"),
        GraphNode(
            uid="code:function:a.py::foo",
            kind="code:function",
            label="foo",
            file_path="a.py",
            start_line=1,
        ),
    ]
    edges = [
        GraphEdge(
            source_uid="code:file:a.py",
            target_uid="code:function:a.py::foo",
            edge_type="contains",
            extractor="test",
            confidence=1.0,
        ),
    ]
    backend.bulk_upsert(nodes, edges)
    try:
        yield backend
    finally:
        graph._BACKEND_SINGLETON = None


# --- cos_graph_export -------------------------------------------------------


def test_export_empty_graph_accepts_valid_edge_type(empty_backend):
    # The exact Hub ContainsTree call on a fresh project: edge_types='contains'.
    res = _parse(graph.cos_graph_export(edge_types=["contains"], mode="containment"))
    assert res["ok"] is True, res
    assert res["data"]["edges"] == []


def test_export_empty_graph_rejects_typo_edge_type(empty_backend):
    res = _parse(graph.cos_graph_export(edge_types=["contians"], mode="containment"))  # typo
    assert res["ok"] is False
    assert res["error"]["category"] == "validation"
    assert "contians" in res["error"]["message"]


def test_export_sparse_graph_accepts_valid_absent_edge_type(contains_only_backend):
    # 'calls' is a valid edge type with zero rows in this docs-only graph →
    # ok([]), NOT a validation fail (the bug a plain empty-check would miss).
    res = _parse(graph.cos_graph_export(edge_types=["calls"], mode="dependencies"))
    assert res["ok"] is True, res
    assert res["data"]["edges"] == []


# --- cos_graph_centrality ---------------------------------------------------


def test_centrality_empty_graph_accepts_valid_kind(empty_backend):
    res = _parse(graph.cos_graph_centrality(kind="function"))
    assert res["ok"] is True, res


def test_centrality_empty_graph_rejects_typo_kind(empty_backend):
    res = _parse(graph.cos_graph_centrality(kind="funktion"))  # typo
    assert res["ok"] is False
    assert res["error"]["category"] == "validation"


# --- drift guards on _KNOWN_EDGE_TYPES --------------------------------------


def test_known_edge_types_superset_of_query_tuples():
    """Every edge_type the tool layer FILTERS on must be in _KNOWN_EDGE_TYPES,
    else that filter would be wrongly rejected on a populated graph."""
    from graph_os import communities

    referenced: set[str] = set()
    referenced.update(graph._SEMANTIC_EDGES)
    referenced.update(graph._CONTAINS_EDGES)
    referenced.update(graph._BEHAVIOURAL_EDGE_TYPES)
    for _label, types in graph._AUTO_BLEND_BUCKETS:
        referenced.update(types)
    referenced.update(communities._PROCESS_EDGE_TYPES)

    missing = referenced - graph._KNOWN_EDGE_TYPES
    assert not missing, f"query-layer edge types missing from _KNOWN_EDGE_TYPES: {sorted(missing)}"


def test_known_edge_types_covers_emitted_literals():
    """Every `edge_type="..."` literal an extractor emits must be in
    _KNOWN_EDGE_TYPES, so a new extractor type can't be silently rejected by
    export validation. Catches direct-emission drift; dict-mapped emissions are
    covered by the superset test + the regression tests above."""
    extractors_dir = Path(graph.__file__).resolve().parent.parent / "extractors"
    pattern = re.compile(r"""edge_type\s*=\s*["']([a-zA-Z_]+)["']""")
    emitted: set[str] = set()
    for py in extractors_dir.glob("*.py"):
        emitted.update(pattern.findall(py.read_text(encoding="utf-8")))

    assert emitted, "no edge_type literals found — extractor path wrong?"
    missing = emitted - graph._KNOWN_EDGE_TYPES
    assert not missing, f"extractor-emitted edge types missing from _KNOWN_EDGE_TYPES: {sorted(missing)}"
