"""A zero from `cos_graph_references` must mean "nothing points here".

Eight node kinds — rule, skill, task, route, tool, event, dependency, contract —
had no entry in the per-kind default map, so a bare call queried the *code*
edge types (calls / accesses_field / imports / references_doc) against nodes
whose only inbound edges are structural. 1,538 edges in this repo's own graph
answered `total_count: 0` with `result_truncated: false`: a complete query of
the wrong edges, indistinguishable from an orphan.

Two guards: the map now covers those kinds, and any empty result names the edge
types that do exist, so the next unmapped kind reports itself instead of lying.
"""

from __future__ import annotations

import json

import pytest

from graph_os.tools import graph
from graph_os.types import GraphEdge, GraphNode


@pytest.fixture()
def structural_backend(migrated_conn, monkeypatch):
    from graph_os.backends.sqlite_backend import SqliteBackend

    backend = SqliteBackend(conn=migrated_conn)
    graph._BACKEND_SINGLETON = backend
    monkeypatch.setattr(graph, "_backend", lambda *, backend=None: graph._BACKEND_SINGLETON)

    for node in (
        GraphNode(uid="folder:src/core/rules", kind="folder", label="rules"),
        GraphNode(
            uid="doc:file:src/core/rules/demo.md",
            kind="rule",
            label="demo",
            file_path="src/core/rules/demo.md",
        ),
        GraphNode(
            uid="code:function:lonely.py::orphan",
            kind="function",
            label="orphan",
            file_path="lonely.py",
        ),
    ):
        backend.upsert_node(node)
    backend.upsert_edge(
        GraphEdge(
            source_uid="folder:src/core/rules",
            target_uid="doc:file:src/core/rules/demo.md",
            edge_type="contains",
            extractor="test",
            confidence=1.0,
        )
    )
    return backend


def _data(envelope) -> dict:
    env = json.loads(envelope) if isinstance(envelope, str) else envelope
    assert env["ok"] is True, env
    return env["data"]


def test_rule_node_reports_its_inbound_edge(structural_backend) -> None:
    data = _data(graph.cos_graph_references("doc:file:src/core/rules/demo.md"))

    assert data["meta"]["node_kind"] == "rule"
    assert data["meta"]["default_kinds_picked"] is True
    assert data["total_count"] == 1, "a rule node with a contains edge must not report zero"


def test_empty_result_names_the_edge_types_that_exist(structural_backend) -> None:
    data = _data(
        graph.cos_graph_references("doc:file:src/core/rules/demo.md", kinds="calls,imports")
    )

    assert data["total_count"] == 0
    assert data["meta"]["result_truncated"] is False
    assert data["meta"]["zero_from_kind_filter"] is True
    assert data["meta"]["edge_types_present"] == ["contains"]


def test_a_genuine_orphan_is_not_flagged(structural_backend) -> None:
    """No inbound edge of any type — zero is the honest answer, unqualified."""
    data = _data(graph.cos_graph_references("code:function:lonely.py::orphan"))

    assert data["total_count"] == 0
    assert "zero_from_kind_filter" not in data["meta"]
    assert "edge_types_present" not in data["meta"]
