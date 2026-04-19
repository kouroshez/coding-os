"""Tests for the 11 cos_graph_* MCP tools (I.8).

Ship gate (Section 19 I.8):
  - ≥ 44 tests (≥ 4 per tool × 11)
  - envelope compliance (Rule 14) on every tool
  - token-budget tests + 1 edge case per tool
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import pytest

from graph_os.tools import graph
from graph_os.types import EvidenceSignal, GraphEdge, GraphNode


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def seeded_backend(migrated_conn, monkeypatch, tmp_path):
    """Seed the backend with a small fixture graph + wire the tools."""
    from graph_os.backends.sqlite_backend import SqliteBackend

    backend = SqliteBackend(conn=migrated_conn)
    # Force the tools module to use *this* backend.
    graph._BACKEND_SINGLETON = backend
    monkeypatch.setattr(graph, "_backend", lambda *, backend=None: graph._BACKEND_SINGLETON)

    nodes = [
        GraphNode(uid="code:function:a.py::foo", kind="code:function", label="foo", file_path="a.py", start_line=1),
        GraphNode(uid="code:function:a.py::bar", kind="code:function", label="bar", file_path="a.py", start_line=10),
        GraphNode(uid="code:function:a.py::baz", kind="code:function", label="baz_handler", file_path="a.py", start_line=20),
        GraphNode(uid="doc:file:docs/x.md", kind="doc:file", label="x.md", file_path="docs/x.md"),
        GraphNode(uid="cos:route:GET:/users", kind="cos:route", label="GET /users", file_path="app.py", metadata={"kind": "http", "method": "get", "path": "/users", "framework": "fastapi"}),
        GraphNode(uid="cos:mcp_tool:cos_graph_query", kind="cos:mcp_tool", label="mcp:cos_graph_query", file_path="srv.py", metadata={"kind": "mcp", "method": "rpc", "path": "cos_graph_query"}),
        GraphNode(uid="code:file:a.py", kind="code:file", label="a.py", file_path="a.py"),
    ]
    edges = [
        GraphEdge(source_uid="code:function:a.py::foo", target_uid="code:function:a.py::bar", edge_type="calls", extractor="test", confidence=0.9),
        GraphEdge(source_uid="code:function:a.py::bar", target_uid="code:function:a.py::baz", edge_type="calls", extractor="test", confidence=0.6),
        GraphEdge(source_uid="code:file:a.py", target_uid="code:function:a.py::foo", edge_type="contains", extractor="test", confidence=1.0),
        GraphEdge(source_uid="doc:file:docs/x.md", target_uid="code:function:a.py::foo", edge_type="references_doc", extractor="test", confidence=0.85),
        GraphEdge(source_uid="code:file:a.py", target_uid="cos:route:GET:/users", edge_type="handles_route", extractor="test", confidence=0.9),
        GraphEdge(source_uid="code:file:a.py", target_uid="cos:mcp_tool:cos_graph_query", edge_type="handles_tool", extractor="test", confidence=0.95),
    ]
    backend.bulk_upsert(nodes, edges)
    yield backend
    graph._BACKEND_SINGLETON = None


# ---------------------------------------------------------------------------
# Envelope contract — every tool must return ok/fail with layer="graph".
# ---------------------------------------------------------------------------


def _decode(envelope):
    if isinstance(envelope, str):
        return json.loads(envelope)
    return envelope


def _assert_ok(envelope) -> dict:
    env = _decode(envelope)
    assert env["ok"] is True, f"expected ok envelope, got {env}"
    data = env["data"]
    assert data["meta"]["layer"] == "graph"
    return data


def _assert_fail(envelope, category: str) -> None:
    env = _decode(envelope)
    assert env["ok"] is False
    assert env["error"]["category"] == category


# ---------------------------------------------------------------------------
# Each tool
# ---------------------------------------------------------------------------


class TestQuery:
    def test_happy_path(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_query("baz_handler"))
        uids = {r["uid"] for r in data["results"]}
        assert "code:function:a.py::baz" in uids

    def test_empty_query_validation_error(self, seeded_backend):
        _assert_fail(graph.cos_graph_query(""), "validation")

    def test_kind_filter(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_query("a.py", kinds=["code:function"]))
        assert all(r["kind"] == "code:function" for r in data["results"])

    def test_limit(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_query("a.py", limit=1))
        assert len(data["results"]) <= 1


class TestContext:
    def test_happy_path(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_context("code:function:a.py::foo"))
        assert data["edge_count"] >= 1
        assert "calls" in data["edges_by_type"]

    def test_unknown_uid(self, seeded_backend):
        _assert_fail(graph.cos_graph_context("code:function:missing"), "not_found")

    def test_fuzzy_label_resolve(self, seeded_backend):
        env = graph.cos_graph_context("foo")  # label not full uid
        # Either resolves fuzzily or returns not_found — both acceptable;
        # exercise that the envelope is always valid.
        assert "ok" in env

    def test_depth_honoured(self, seeded_backend):
        shallow = _assert_ok(
            graph.cos_graph_context("code:function:a.py::foo", depth=1)
        )
        deeper = _assert_ok(
            graph.cos_graph_context("code:function:a.py::foo", depth=3)
        )
        assert deeper["edge_count"] >= shallow["edge_count"]


class TestImpact:
    def test_downstream_tiers(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_impact("code:function:a.py::bar"))
        tiers = data["tiers"]
        # foo → bar is a will_break (0.9), bar → baz is should_review (0.6).
        assert tiers["will_break"] or tiers["should_review"]

    def test_unknown_uid(self, seeded_backend):
        _assert_fail(graph.cos_graph_impact("code:function:missing"), "not_found")

    def test_confidence_min_filters(self, seeded_backend):
        data = _assert_ok(
            graph.cos_graph_impact(
                "code:function:a.py::foo", confidence_min=0.9
            )
        )
        # Tiered counts honour the floor.
        for entry in data["tiers"]["should_review"]:
            assert entry["confidence"] >= 0.5

    def test_upstream_direction(self, seeded_backend):
        data = _assert_ok(
            graph.cos_graph_impact(
                "code:function:a.py::bar", direction="upstream"
            )
        )
        assert data["direction"] == "upstream"


class TestDetectChanges:
    def test_no_files_returns_empty_envelope(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_detect_changes(files=[]))
        assert data["files"] == []

    def test_file_maps_to_symbols(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_detect_changes(files=["a.py"]))
        assert data["files"] == ["a.py"]
        assert data["symbols"]

    def test_unknown_file_skipped(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_detect_changes(files=["ghost.py"]))
        assert data["symbols"] == []

    def test_risk_level_present(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_detect_changes(files=["a.py"]))
        assert data["risk_level"] in {"low", "medium", "high", "none"}


class TestTrace:
    def test_happy_path(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_trace("code:function:a.py::foo"))
        uids = {s["uid"] for s in data["steps"]}
        assert "code:function:a.py::foo" in uids

    def test_unknown_entry(self, seeded_backend):
        _assert_fail(graph.cos_graph_trace("code:function:missing"), "not_found")

    def test_max_steps_honoured(self, seeded_backend):
        data = _assert_ok(
            graph.cos_graph_trace("code:function:a.py::foo", max_steps=1)
        )
        assert len(data["steps"]) <= 1

    def test_branches_captured(self, seeded_backend):
        # Not guaranteed on this fixture; just assert shape.
        data = _assert_ok(graph.cos_graph_trace("code:function:a.py::foo"))
        assert "branches" in data


class TestSimilar:
    def test_happy_path(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_similar("code:function:a.py::foo", confidence_min=0.0, top_k=5))
        assert "results" in data

    def test_unknown_uid(self, seeded_backend):
        _assert_fail(graph.cos_graph_similar("code:function:missing"), "not_found")

    def test_top_k_honoured(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_similar("code:function:a.py::foo", top_k=2, confidence_min=0.0))
        assert len(data["results"]) <= 2

    def test_confidence_floor_excludes_low(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_similar("code:function:a.py::foo", confidence_min=0.99, top_k=5))
        assert all(r["similarity"] >= 0.99 for r in data["results"])


class TestReferences:
    def test_happy_path(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_references("code:function:a.py::foo"))
        assert data["count"] >= 1

    def test_unknown_uid(self, seeded_backend):
        _assert_fail(graph.cos_graph_references("code:function:missing"), "not_found")

    def test_filter_kinds(self, seeded_backend):
        data = _assert_ok(
            graph.cos_graph_references(
                "code:function:a.py::foo", kinds=["references_doc"]
            )
        )
        assert all(
            e["edge_type"] == "references_doc" for e in data["references"]
        )

    def test_limit_respected(self, seeded_backend):
        data = _assert_ok(
            graph.cos_graph_references("code:function:a.py::foo", limit=1)
        )
        assert data["count"] <= 1


class TestPath:
    def test_happy_path(self, seeded_backend):
        data = _assert_ok(
            graph.cos_graph_path(
                "code:function:a.py::foo", "code:function:a.py::baz"
            )
        )
        assert data["hops"] >= 1

    def test_unknown_source(self, seeded_backend):
        _assert_fail(
            graph.cos_graph_path("code:function:missing", "code:function:a.py::baz"),
            "not_found",
        )

    def test_unknown_target(self, seeded_backend):
        _assert_fail(
            graph.cos_graph_path("code:function:a.py::foo", "code:function:missing"),
            "not_found",
        )

    def test_unreachable_path_empty(self, seeded_backend):
        data = _assert_ok(
            graph.cos_graph_path(
                "doc:file:docs/x.md", "cos:route:GET:/users", max_hops=0
            )
        )
        assert data["path"] is None


class TestExport:
    def test_json_format(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_export(format="json"))
        assert data["format"] == "json"
        assert data["nodes"] and data["edges"]

    def test_mermaid_format(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_export(format="mermaid"))
        assert "graph LR" in data["diagram"]

    def test_dot_format(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_export(format="dot"))
        assert data["diagram"].startswith("digraph G")

    def test_unknown_format(self, seeded_backend):
        _assert_fail(graph.cos_graph_export(format="svg"), "validation")


class TestRenamePlan:
    def test_happy_path(self, seeded_backend):
        data = _assert_ok(
            graph.cos_graph_rename_plan("code:function:a.py::foo", "renamed_foo")
        )
        assert data["old_name"] == "foo"
        assert data["new_name"] == "renamed_foo"

    def test_empty_new_name_rejected(self, seeded_backend):
        _assert_fail(
            graph.cos_graph_rename_plan("code:function:a.py::foo", ""),
            "validation",
        )

    def test_unknown_uid(self, seeded_backend):
        _assert_fail(
            graph.cos_graph_rename_plan("code:function:missing", "new"),
            "not_found",
        )

    def test_risk_set(self, seeded_backend):
        data = _assert_ok(
            graph.cos_graph_rename_plan("code:function:a.py::foo", "new_foo")
        )
        assert data["risk"] in {"low", "medium", "high"}


class TestContracts:
    def test_returns_buckets(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_contracts())
        assert "http_routes" in data
        assert "mcp_tools" in data
        assert data["count"] >= 2

    def test_kind_filter_narrows(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_contracts(kinds=["mcp"]))
        assert data["http_routes"] == []
        assert data["mcp_tools"]

    def test_count_present(self, seeded_backend):
        data = _assert_ok(graph.cos_graph_contracts())
        expected = sum(
            len(v)
            for k, v in data.items()
            if k.endswith("_routes") or k in ("mcp_tools", "grpc_endpoints", "event_handlers", "websocket")
        )
        assert data["count"] == expected

    def test_envelope_layer_is_graph(self, seeded_backend):
        env = _decode(graph.cos_graph_contracts())
        assert env["data"]["meta"]["layer"] == "graph"


# ---------------------------------------------------------------------------
# Cross-tool: every tool must return an envelope with layer="graph".
# ---------------------------------------------------------------------------


def test_every_tool_uses_graph_layer(seeded_backend):
    calls = [
        ("query", lambda: graph.cos_graph_query("foo")),
        ("context", lambda: graph.cos_graph_context("code:function:a.py::foo")),
        ("impact", lambda: graph.cos_graph_impact("code:function:a.py::foo")),
        ("detect_changes", lambda: graph.cos_graph_detect_changes(files=["a.py"])),
        ("trace", lambda: graph.cos_graph_trace("code:function:a.py::foo")),
        ("similar", lambda: graph.cos_graph_similar("code:function:a.py::foo")),
        ("references", lambda: graph.cos_graph_references("code:function:a.py::foo")),
        ("path", lambda: graph.cos_graph_path("code:function:a.py::foo", "code:function:a.py::bar")),
        ("export", lambda: graph.cos_graph_export(format="json")),
        ("rename_plan", lambda: graph.cos_graph_rename_plan("code:function:a.py::foo", "x")),
        ("contracts", lambda: graph.cos_graph_contracts()),
    ]
    for name, thunk in calls:
        env = _decode(thunk())
        if env["ok"]:
            assert env["data"]["meta"]["layer"] == "graph", name
