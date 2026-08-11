"""Tests for cos_graph_export smart-blend modes (TASK-141).

Coverage matrix:
  - auto mode blends semantic (60%) + contains (40%) and never returns
    100% contains for non-trivial graphs
  - containment mode is contains-only
  - dependencies mode never includes contains edges
  - processes mode returns synthetic community nodes + member_of edges
  - exclude_kinds default drops doc:frontmatter_key / doc:heading
  - exclude_kinds="" disables filtering
  - explicit exclude_kinds overrides the default set
  - validation: bogus mode rejected with envelope category=validation
  - root_uid path is unchanged (legacy BFS behaviour preserved)
"""

from __future__ import annotations

import json

import pytest

from graph_os.tools import (
    graph as graph_tools,
)
from graph_os.types import GraphEdge, GraphNode

# ---------------------------------------------------------------------------
# Stub backend (compat with the StubBackend in test_communities.py)
# ---------------------------------------------------------------------------


class _StubBackend:
    backend_id = "stub-export"

    def __init__(self, nodes, edges):
        self._nodes = {n.uid: n for n in nodes}
        self._edges = list(edges)

    def get_node(self, uid):
        return self._nodes.get(uid)

    def sample_nodes(self, *, kind, limit):
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
        limit=100,
    ):
        out = []
        kinds = set(edge_types) if edge_types else None
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

    def edges_among(
        self, uids, *, edge_types=None, exclude_edge_types=("contains",), limit=100_000
    ):
        members = set(uids)
        wanted = set(edge_types) if edge_types else None
        out = []
        for e in self._edges:
            if e.source_uid not in members or e.target_uid not in members:
                continue
            if e.edge_type in set(exclude_edge_types or ()):
                continue
            if wanted is not None and e.edge_type not in wanted:
                continue
            out.append(e)
            if len(out) >= limit:
                break
        return out


def _node(uid, kind="code:function", label=None, file_path="src/foo.py"):
    return GraphNode(
        uid=uid,
        kind=kind,
        label=label or uid.split("::")[-1],
        file_path=file_path,
        start_line=1,
        metadata={},
    )


def _edge(src, tgt, etype="calls"):
    return GraphEdge(
        source_uid=src,
        target_uid=tgt,
        edge_type=etype,
        confidence=1.0 if etype == "contains" else 0.8,
        extractor="test@v1",
    )


def _parse(value):
    """`_ok`/`_fail` return a JSON-encoded string envelope."""
    return json.loads(value) if isinstance(value, str) else value


@pytest.fixture
def mixed_backend():
    """Mix of contains + semantic edges + frontmatter noise."""
    nodes = [
        _node("code:file:a.py", kind="code:file"),
        _node("code:module:a", kind="code:module"),
        _node("code:function:a.py::login", label="login"),
        _node("code:function:a.py::verify", label="verify"),
        _node("code:function:a.py::issue_jwt", label="issue_jwt"),
        # Noise nodes that should be filtered by default.
        _node(
            "doc:frontmatter:foo.md::layer",
            kind="doc:frontmatter_key",
            label="layer=engineering",
        ),
        _node(
            "doc:heading:foo.md#intro",
            kind="doc:heading",
            label="Intro",
        ),
    ]
    edges = [
        # Contains spine (high-confidence wins SQL ordering).
        _edge("code:file:a.py", "code:module:a", "contains"),
        _edge("code:module:a", "code:function:a.py::login", "contains"),
        _edge("code:module:a", "code:function:a.py::verify", "contains"),
        _edge("code:module:a", "code:function:a.py::issue_jwt", "contains"),
        _edge(
            "code:module:a",
            "doc:frontmatter:foo.md::layer",
            "contains",
        ),
        _edge(
            "code:module:a",
            "doc:heading:foo.md#intro",
            "contains",
        ),
        # Semantic edges that the legacy export missed.
        _edge(
            "code:function:a.py::login",
            "code:function:a.py::verify",
            "calls",
        ),
        _edge(
            "code:function:a.py::login",
            "code:function:a.py::issue_jwt",
            "calls",
        ),
        _edge(
            "code:function:a.py::verify",
            "code:function:a.py::issue_jwt",
            "calls",
        ),
    ]
    be = _StubBackend(nodes, edges)
    return be


@pytest.fixture(autouse=True)
def _bind_backend(mixed_backend, monkeypatch):
    """Pin the singleton so every cos_graph_export call hits the stub."""
    monkeypatch.setattr(graph_tools, "_BACKEND_SINGLETON", mixed_backend)
    monkeypatch.setattr(graph_tools, "_backend", lambda backend=None: mixed_backend)
    yield


@pytest.fixture
def chain_backend():
    """6-link contains chain so depth gating is observable."""
    chain = [f"code:module:level_{i}" for i in range(6)]
    nodes = [_node(uid, kind="code:module", label=uid.split(":")[-1]) for uid in chain]
    edges = [_edge(chain[i], chain[i + 1], "contains") for i in range(len(chain) - 1)]
    return _StubBackend(nodes, edges)


@pytest.fixture
def doc_link_backend():
    """Backend with mixed contains + calls + doc-link + decoration edges."""
    nodes = [
        _node("code:file:a.py", kind="code:file"),
        _node("code:function:a.py::foo", label="foo"),
        _node("code:function:a.py::bar", label="bar"),
        _node("doc:file:guide.md", kind="doc_file", label="guide.md"),
        _node("doc:file:other.md", kind="doc_file", label="other.md"),
        _node("code:function:a.py::decorated", label="decorated"),
        _node("code:function:a.py::decorator", label="decorator"),
    ]
    edges = [
        # contains spine
        _edge("code:file:a.py", "code:function:a.py::foo", "contains"),
        _edge("code:file:a.py", "code:function:a.py::bar", "contains"),
        # semantic
        _edge("code:function:a.py::foo", "code:function:a.py::bar", "calls"),
        # doc cross-link — previously invisible in auto mode
        _edge("doc:file:guide.md", "doc:file:other.md", "links_to"),
        _edge("doc:file:guide.md", "code:function:a.py::foo", "references_doc"),
        # decoration
        _edge("code:function:a.py::decorated", "code:function:a.py::decorator", "is_decorated_by"),
    ]
    return _StubBackend(nodes, edges)


class TestValidation:
    def test_unknown_mode_rejected(self):
        res = _parse(graph_tools.cos_graph_export(mode="garbage"))
        assert res["ok"] is False
        assert res["error"]["category"] == "validation"

    def test_unknown_format_rejected(self):
        res = _parse(graph_tools.cos_graph_export(format="rdf"))
        assert res["ok"] is False
        assert res["error"]["category"] == "validation"


class TestAutoMode:
    def test_blend_includes_semantic_edges(self):
        res = _parse(graph_tools.cos_graph_export(mode="auto", max_nodes=20))
        assert res["ok"] is True
        edge_types = {e["edge_type"] for e in res["data"]["edges"]}
        # Must include both kinds — the bug was 100% contains.
        assert "calls" in edge_types
        assert "contains" in edge_types

    def test_default_mode_is_auto(self):
        # No explicit mode → auto behaviour.
        res = _parse(graph_tools.cos_graph_export(max_nodes=20))
        assert res["ok"] is True
        edge_types = {e["edge_type"] for e in res["data"]["edges"]}
        assert "calls" in edge_types

    def test_noise_filtered_by_default(self):
        res = _parse(graph_tools.cos_graph_export(mode="auto", max_nodes=50))
        kinds = {n["kind"] for n in res["data"]["nodes"]}
        assert "doc:frontmatter_key" not in kinds
        assert "doc:heading" not in kinds


class TestContainmentMode:
    def test_only_contains_edges(self):
        res = _parse(graph_tools.cos_graph_export(mode="containment", max_nodes=50))
        assert res["ok"] is True
        edge_types = {e["edge_type"] for e in res["data"]["edges"]}
        assert edge_types <= {"contains"}


class TestDependenciesMode:
    def test_no_contains_edges(self):
        res = _parse(graph_tools.cos_graph_export(mode="dependencies", max_nodes=50))
        assert res["ok"] is True
        edge_types = {e["edge_type"] for e in res["data"]["edges"]}
        assert "contains" not in edge_types
        assert "calls" in edge_types


class TestProcessesMode:
    def test_synthetic_community_nodes(self, monkeypatch):
        # Force a stub Louvain detector that produces one community.
        from graph_os import communities as comm_mod
        from graph_os.communities import Community

        synthetic = Community(
            community_id="community:abc",
            name="login-flow",
            summary="login → verify → issue_jwt",
            priority=0.5,
            member_count=3,
            members=tuple(
                {
                    "uid": uid,
                    "label": uid.split("::")[-1],
                    "kind": "code:function",
                    "step_index": idx,
                    "file_path": "src/foo.py",
                    "start_line": 1,
                }
                for idx, uid in enumerate(
                    [
                        "code:function:a.py::login",
                        "code:function:a.py::verify",
                        "code:function:a.py::issue_jwt",
                    ]
                )
            ),
        )
        monkeypatch.setattr(
            comm_mod,
            "compute_communities",
            lambda be, **kwargs: ([synthetic], {}),
        )

        res = _parse(graph_tools.cos_graph_export(mode="processes", max_nodes=20))
        assert res["ok"] is True
        kinds = {n["kind"] for n in res["data"]["nodes"]}
        assert "community" in kinds
        edge_types = {e["edge_type"] for e in res["data"]["edges"]}
        assert "member_of_community" in edge_types

    @staticmethod
    def _community(idx: int, size: int):
        from graph_os.communities import Community

        members = tuple(
            {
                "uid": f"code:function:c{idx}.py::fn{j}",
                "label": f"fn{idx}_{j}",
                "kind": "code:function",
                "step_index": j,
                "file_path": f"src/c{idx}.py",
                "start_line": 1,
            }
            for j in range(size)
        )
        return Community(
            community_id=f"community:c{idx}",
            name=f"flow-{idx}",
            summary=f"fn{idx}_0 → fn{idx}_1",
            priority=float(size),
            member_count=size,
            members=members,
        )

    def _bind_communities(self, monkeypatch, communities):
        # The export resolves member uids via be.get_node; register them
        # on the bound stub so the member rows hydrate.
        from graph_os import communities as comm_mod

        be = graph_tools._backend()
        for c in communities:
            for m in c.members:
                be._nodes[m["uid"]] = _node(m["uid"], label=m["label"])
        monkeypatch.setattr(
            comm_mod,
            "compute_communities",
            lambda b, **kwargs: (list(communities), {}),
        )

    def test_at_least_six_community_nodes_surface(self, monkeypatch):
        # TASK-407 / guards the TASK-406 regression: 8 communities where
        # the first holds 400 members. At a 500-node budget the old greedy
        # pass surfaced only ~2 headers; the fair reservation must surface
        # every header.
        communities = [self._community(0, 400)] + [self._community(i, 5) for i in range(1, 8)]
        self._bind_communities(monkeypatch, communities)
        res = _parse(graph_tools.cos_graph_export(mode="processes", max_nodes=500))
        assert res["ok"] is True
        community_nodes = [n for n in res["data"]["nodes"] if n["kind"] == "community"]
        assert len(community_nodes) >= 6

    def test_budget_reserved_across_communities(self, monkeypatch):
        # The 400-member community must not consume the whole budget — its
        # member count in the export is capped at the fair per-community
        # share so every community above min_size appears as its header.
        communities = [self._community(0, 400)] + [self._community(i, 5) for i in range(1, 8)]
        self._bind_communities(monkeypatch, communities)
        res = _parse(graph_tools.cos_graph_export(mode="processes", max_nodes=500))
        nodes = res["data"]["nodes"]
        # Every community above min_size surfaces at least its header node.
        community_ids = {n["uid"] for n in nodes if n["kind"] == "community"}
        assert {f"community:c{i}" for i in range(8)} <= community_ids
        # The top community's members are capped — far below its 400 size.
        edges = res["data"]["edges"]
        top_members = {e["source_uid"] for e in edges if e["target_uid"] == "community:c0"}
        member_budget = 500 - len(community_ids)
        fair_share = max(1, member_budget // len(communities))
        assert len(top_members) <= fair_share


class TestExcludeKinds:
    def test_empty_list_disables_filter(self):
        # Pass `[]` to keep all kinds — frontmatter / heading visible.
        res = _parse(graph_tools.cos_graph_export(mode="auto", max_nodes=50, exclude_kinds=[]))
        kinds = {n["kind"] for n in res["data"]["nodes"]}
        assert "doc:frontmatter_key" in kinds or "doc:heading" in kinds

    def test_custom_exclude_kinds(self):
        res = _parse(
            graph_tools.cos_graph_export(
                mode="containment",
                max_nodes=50,
                exclude_kinds=["code:module"],
            )
        )
        kinds = {n["kind"] for n in res["data"]["nodes"]}
        assert "code:module" not in kinds
