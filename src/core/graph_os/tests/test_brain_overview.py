"""Tests for cos_graph_overview — module-level brain overview (TASK-141a).

Coverage matrix:
  - aggregates files into module nodes by parent directory
  - cross-module semantic edges land with correct weights
  - same-module edges are dropped (loops would clutter the canvas)
  - excluded segments (.venv, claude/worktrees, dist) skip silently
  - max_modules clamp keeps only the heaviest contributors
  - min_edge_weight prunes lightweight edges
  - validation rejects bogus inputs with envelope category=validation
  - empty graph returns empty result, not failure
  - module nodes carry metadata.member_count + languages
"""

from __future__ import annotations

import json

import pytest

from graph_os.tools import graph as graph_tools
from graph_os.types import GraphEdge, GraphNode


class _StubBackend:
    backend_id = "stub-overview"

    def __init__(self, nodes, edges):
        self._nodes = {n.uid: n for n in nodes}
        self._edges = list(edges)

    def get_node(self, uid):
        return self._nodes.get(uid)

    def sample_nodes(self, kind, limit):
        if kind is None:
            return list(self._nodes.values())[:limit]
        return [n for n in self._nodes.values() if n.kind == kind][:limit]

    def list_edges(
        self,
        *,
        source_uid=None,
        target_uid=None,
        edge_types=None,
        confidence_min=0.0,
        include_evidence=False,
        limit=100,
    ):
        kinds = set(edge_types) if edge_types else None
        out = []
        for e in self._edges:
            if source_uid is not None and e.source_uid != source_uid:
                continue
            if target_uid is not None and e.target_uid != target_uid:
                continue
            if kinds is not None and e.edge_type not in kinds:
                continue
            out.append(e)
            if len(out) >= limit:
                break
        return out

    def count_edges(self, edge_type=None):
        if edge_type is None:
            return len(self._edges)
        return sum(1 for e in self._edges if e.edge_type == edge_type)


def _node(uid, *, kind, file_path, lang="py"):
    return GraphNode(
        uid=uid,
        kind=kind,
        label=uid.split("/")[-1],
        file_path=file_path,
        start_line=1,
        lang=lang,
        metadata={},
    )


def _edge(src, tgt, etype):
    return GraphEdge(
        source_uid=src,
        target_uid=tgt,
        edge_type=etype,
        confidence=1.0,
        extractor="test@v1",
    )


def _parse(value):
    return json.loads(value) if isinstance(value, str) else value


@pytest.fixture
def small_repo_backend():
    """3 modules: cli, core/graph_os, core/graph_os/extractors.

    Edges:
      cli imports core/graph_os (3 calls aggregated into weight=3)
      core/graph_os/extractors imports core/graph_os (1)
      cli internal call (same module — should NOT appear in result)
    """
    nodes = [
        _node("code:file:cli/main.py", kind="code:file", file_path="cli/main.py"),
        _node("code:function:cli/main.py::run", kind="code:function", file_path="cli/main.py"),
        _node("code:function:cli/main.py::helper", kind="code:function", file_path="cli/main.py"),
        _node("code:file:core/graph_os/types.py", kind="code:file", file_path="core/graph_os/types.py"),
        _node("code:function:core/graph_os/types.py::norm", kind="code:function", file_path="core/graph_os/types.py"),
        _node(
            "code:file:core/graph_os/extractors/code_python.py",
            kind="code:file",
            file_path="core/graph_os/extractors/code_python.py",
        ),
        _node(
            "code:function:core/graph_os/extractors/code_python.py::extract",
            kind="code:function",
            file_path="core/graph_os/extractors/code_python.py",
        ),
        # Excluded — should be dropped because path matches claude/worktrees prefix.
        _node(
            "code:file:claude/worktrees/agent-x/foo.py",
            kind="code:file",
            file_path="claude/worktrees/agent-x/foo.py",
        ),
    ]
    edges = [
        # cli main.py contains its functions
        _edge("code:file:cli/main.py", "code:function:cli/main.py::run", "contains"),
        _edge("code:file:cli/main.py", "code:function:cli/main.py::helper", "contains"),
        _edge(
            "code:file:core/graph_os/types.py",
            "code:function:core/graph_os/types.py::norm",
            "contains",
        ),
        _edge(
            "code:file:core/graph_os/extractors/code_python.py",
            "code:function:core/graph_os/extractors/code_python.py::extract",
            "contains",
        ),
        # cross-module imports (should aggregate)
        _edge("code:file:cli/main.py", "code:file:core/graph_os/types.py", "imports"),
        _edge(
            "code:function:cli/main.py::run",
            "code:function:core/graph_os/types.py::norm",
            "calls",
        ),
        _edge(
            "code:function:cli/main.py::helper",
            "code:function:core/graph_os/types.py::norm",
            "calls",
        ),
        _edge(
            "code:file:core/graph_os/extractors/code_python.py",
            "code:file:core/graph_os/types.py",
            "imports",
        ),
        # Same-module edge — must NOT appear in overview output.
        _edge(
            "code:function:cli/main.py::run",
            "code:function:cli/main.py::helper",
            "calls",
        ),
    ]
    return _StubBackend(nodes, edges)


def test_aggregates_files_into_modules(small_repo_backend, monkeypatch):
    monkeypatch.setattr(graph_tools, "_backend", lambda **_: small_repo_backend)
    res = _parse(graph_tools.cos_graph_overview(max_modules=10))
    assert res["ok"]
    paths = {n["uid"] for n in res["data"]["nodes"]}
    assert "module:cli" in paths
    assert "module:core/graph_os" in paths
    assert "module:core/graph_os/extractors" in paths


def test_cross_module_edges_aggregate_with_weights(small_repo_backend, monkeypatch):
    monkeypatch.setattr(graph_tools, "_backend", lambda **_: small_repo_backend)
    res = _parse(graph_tools.cos_graph_overview(max_modules=10))
    edges = res["data"]["edges"]
    by_pair_type = {(e["source_uid"], e["target_uid"], e["edge_type"]): e["weight"] for e in edges}
    # cli → core/graph_os: 1 import + 2 calls = two distinct edge_types
    assert by_pair_type[("module:cli", "module:core/graph_os", "calls")] == 2
    assert by_pair_type[("module:cli", "module:core/graph_os", "imports")] == 1
    assert by_pair_type[
        ("module:core/graph_os/extractors", "module:core/graph_os", "imports")
    ] == 1


def test_same_module_edges_dropped(small_repo_backend, monkeypatch):
    monkeypatch.setattr(graph_tools, "_backend", lambda **_: small_repo_backend)
    res = _parse(graph_tools.cos_graph_overview(max_modules=10))
    for e in res["data"]["edges"]:
        assert e["source_uid"] != e["target_uid"], "same-module edge leaked into overview"


def test_excluded_segments_dropped(small_repo_backend, monkeypatch):
    monkeypatch.setattr(graph_tools, "_backend", lambda **_: small_repo_backend)
    res = _parse(graph_tools.cos_graph_overview(max_modules=10))
    for n in res["data"]["nodes"]:
        assert "claude/worktrees" not in n["uid"], "worktree noise leaked"
        assert ".venv" not in n["uid"]


def test_max_modules_clamps(small_repo_backend, monkeypatch):
    monkeypatch.setattr(graph_tools, "_backend", lambda **_: small_repo_backend)
    res = _parse(graph_tools.cos_graph_overview(max_modules=2))
    assert len(res["data"]["nodes"]) <= 2
    # surviving modules should be the heaviest hitters (cli has 3 members,
    # core/graph_os has 2, extractors has 2).
    kept = {n["uid"] for n in res["data"]["nodes"]}
    assert "module:cli" in kept


def test_min_edge_weight_prunes(small_repo_backend, monkeypatch):
    monkeypatch.setattr(graph_tools, "_backend", lambda **_: small_repo_backend)
    res = _parse(graph_tools.cos_graph_overview(max_modules=10, min_edge_weight=2))
    weights = [e["weight"] for e in res["data"]["edges"]]
    assert all(w >= 2 for w in weights)
    # At least the calls=2 cli→core/graph_os should survive.
    assert any(
        e["edge_type"] == "calls" and e["weight"] == 2 for e in res["data"]["edges"]
    )


def test_module_metadata_carries_member_count_and_languages(small_repo_backend, monkeypatch):
    monkeypatch.setattr(graph_tools, "_backend", lambda **_: small_repo_backend)
    res = _parse(graph_tools.cos_graph_overview(max_modules=10))
    cli_node = next(n for n in res["data"]["nodes"] if n["uid"] == "module:cli")
    md = cli_node["metadata"]
    assert md["member_count"] == 3
    assert "py" in md["languages"]
    assert md["synthetic"] is True
    assert isinstance(md["sample_files"], list)


def test_validation_rejects_zero_max_modules(small_repo_backend, monkeypatch):
    monkeypatch.setattr(graph_tools, "_backend", lambda **_: small_repo_backend)
    res = _parse(graph_tools.cos_graph_overview(max_modules=0))
    assert res["ok"] is False
    assert res["error"]["category"] == "validation"


def test_validation_rejects_zero_min_edge_weight(small_repo_backend, monkeypatch):
    monkeypatch.setattr(graph_tools, "_backend", lambda **_: small_repo_backend)
    res = _parse(graph_tools.cos_graph_overview(min_edge_weight=0))
    assert res["ok"] is False
    assert res["error"]["category"] == "validation"


def test_empty_graph_returns_empty_result(monkeypatch):
    empty = _StubBackend([], [])
    monkeypatch.setattr(graph_tools, "_backend", lambda **_: empty)
    res = _parse(graph_tools.cos_graph_overview(max_modules=10))
    assert res["ok"]
    assert res["data"]["nodes"] == []
    assert res["data"]["edges"] == []
    assert res["data"]["meta"]["module_count"] == 0


def test_response_meta_layer(small_repo_backend, monkeypatch):
    """Rule 14: every cos_* tool returns layer=graph in meta."""
    monkeypatch.setattr(graph_tools, "_backend", lambda **_: small_repo_backend)
    res = _parse(graph_tools.cos_graph_overview(max_modules=5))
    assert res["data"]["meta"]["layer"] == "graph"
    assert res["data"]["meta"]["backend"] == "stub-overview"
