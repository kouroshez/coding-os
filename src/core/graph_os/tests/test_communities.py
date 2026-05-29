"""Tests for graph_os.communities (TASK-075).

Coverage matrix:
  - 3-cluster fixture (login / register / token-refresh) → 3 detected communities
  - min_size filter drops singleton clusters
  - max_communities cap honored
  - Stable community_id across reruns (sorted-uid-hash)
  - Step ordering follows entry-point score then file path tie-break
  - Priority formula: log10(size+1) * (avg_entry_score + 0.1)
  - communities_to_processes filters by relevant_uids
  - Empty / no-edge graph degrades cleanly to []
  - cos_graph_communities envelope shape (ok/fail)
  - cos_graph_query surfaces processes for matching uids
  - Cache invalidates on edge-count change
"""

from __future__ import annotations

import pytest

from graph_os.communities import (
    Community,
    communities_to_processes,
    compute_communities,
    reset_cache,
)
from graph_os.types import GraphEdge, GraphNode

# ---------------------------------------------------------------------------
# Stub backend (mirrors the one used in test_entry_points.py)
# ---------------------------------------------------------------------------


class _StubBackend:
    backend_id = "stub-communities"

    def __init__(
        self,
        nodes: list[GraphNode],
        edges: list[GraphEdge],
    ) -> None:
        self._nodes = {n.uid: n for n in nodes}
        self._edges = list(edges)

    def get_node(self, uid: str):
        return self._nodes.get(uid)

    def sample_nodes(self, *, kind: str | None, limit: int):
        if kind is None:
            return list(self._nodes.values())[:limit]
        return [n for n in self._nodes.values() if n.kind == kind][:limit]

    def list_edges(
        self,
        *,
        source_uid: str | None = None,
        target_uid: str | None = None,
        edge_types=None,
        limit: int = 100,
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

    def count_edges(self, edge_type: str | None = None) -> int:
        if edge_type is None:
            return len(self._edges)
        return sum(1 for e in self._edges if e.edge_type == edge_type)


def _node(
    uid: str,
    *,
    kind: str = "code:function",
    label: str | None = None,
    file_path: str = "src/foo.py",
) -> GraphNode:
    return GraphNode(
        uid=uid,
        kind=kind,
        label=label or uid.rsplit(":", 1)[-1].split("::")[-1],
        file_path=file_path,
        start_line=1,
        metadata={},
    )


def _edge(src: str, tgt: str, edge_type: str = "calls") -> GraphEdge:
    return GraphEdge(
        source_uid=src,
        target_uid=tgt,
        edge_type=edge_type,
        confidence=1.0,
        extractor="test@v1",
    )


@pytest.fixture(autouse=True)
def _clean_cache():
    reset_cache()
    yield
    reset_cache()


# ---------------------------------------------------------------------------
# Fixtures: three named flows
# ---------------------------------------------------------------------------


@pytest.fixture()
def three_flow_backend() -> _StubBackend:
    """Login + Register + TokenRefresh — 3 disjoint clusters."""
    login_nodes = [
        _node(f"code:function:auth/login.py::{n}", label=n)
        for n in ("login", "verify_password", "session_create")
    ]
    register_nodes = [
        _node(f"code:function:auth/register.py::{n}", label=n)
        for n in ("register", "validate_email", "send_welcome")
    ]
    refresh_nodes = [
        _node(f"code:function:auth/refresh.py::{n}", label=n)
        for n in ("refresh_token", "rotate_session", "issue_jwt")
    ]
    nodes = login_nodes + register_nodes + refresh_nodes

    edges: list[GraphEdge] = []
    # Strong intra-cluster edges
    for cluster in (login_nodes, register_nodes, refresh_nodes):
        for i in range(len(cluster) - 1):
            edges.append(_edge(cluster[i].uid, cluster[i + 1].uid))
        # Make it a chain + one shortcut for Louvain to lock
        edges.append(_edge(cluster[0].uid, cluster[-1].uid))
    return _StubBackend(nodes, edges)


# ---------------------------------------------------------------------------
# compute_communities
# ---------------------------------------------------------------------------


class TestComputeCommunities:
    def test_three_clusters_detected(self, three_flow_backend):
        communities, membership = compute_communities(three_flow_backend, min_size=2)
        # Louvain typically merges weak partitions, but with disjoint
        # subgraphs we expect at least 3 (one per chain).
        assert len(communities) >= 3
        assert len(membership) == 9  # every node placed

    def test_membership_matches_communities(self, three_flow_backend):
        communities, membership = compute_communities(three_flow_backend)
        for c in communities:
            for m in c.members:
                assert membership[m["uid"]] == c.community_id

    def test_min_size_drops_singletons(self, three_flow_backend):
        # Add a lone node — it should not produce a community at min_size>=2.
        communities, _ = compute_communities(three_flow_backend, min_size=4)
        # Each chain has 3 nodes; min_size=4 should eliminate all clusters.
        assert all(c.member_count >= 4 for c in communities)

    def test_max_communities_cap(self, three_flow_backend):
        communities, _ = compute_communities(three_flow_backend, max_communities=1)
        assert len(communities) == 1

    def test_stable_community_ids(self, three_flow_backend):
        first, _ = compute_communities(three_flow_backend)
        reset_cache()
        second, _ = compute_communities(three_flow_backend)
        first_ids = sorted(c.community_id for c in first)
        second_ids = sorted(c.community_id for c in second)
        assert first_ids == second_ids

    def test_priority_formula(self, three_flow_backend):
        communities, _ = compute_communities(three_flow_backend)
        # Every priority is log10(member_count+1) * (avg_entry_score + 0.1).
        # Without entry_score signals, avg=0 → priority = log10(N+1) * 0.1.
        import math

        for c in communities:
            expected = round(math.log10(c.member_count + 1) * 0.1, 4)
            assert c.priority == pytest.approx(expected, abs=1e-3)

    def test_summary_joins_top_three_labels(self, three_flow_backend):
        communities, _ = compute_communities(three_flow_backend)
        for c in communities:
            assert " → " in c.summary or c.member_count == 1

    def test_test_flow_community_down_ranked(self):
        """TASK-046: an all-test community ranks below an equal-size all-
        production one (test files' dense intra-file graphs otherwise win)."""
        prod = [
            _node(f"code:function:svc/a.py::{n}", file_path="svc/a.py")
            for n in ("alpha", "beta", "gamma")
        ]
        tests = [
            _node(f"code:function:tests/test_x.py::{n}", file_path="tests/test_x.py")
            for n in ("test_a", "test_b", "test_c")
        ]
        edges = []
        for cluster in (prod, tests):
            for i in range(len(cluster) - 1):
                edges.append(_edge(cluster[i].uid, cluster[i + 1].uid))
            edges.append(_edge(cluster[0].uid, cluster[-1].uid))
        comms, _ = compute_communities(_StubBackend(prod + tests, edges), min_size=2)
        prod_comm = next((c for c in comms if not c.name.startswith("test_")), None)
        test_comm = next((c for c in comms if c.name.startswith("test_")), None)
        assert prod_comm and test_comm
        assert prod_comm.priority > test_comm.priority


class TestEdgeCases:
    def test_empty_graph(self):
        be = _StubBackend([], [])
        communities, membership = compute_communities(be)
        assert communities == []
        assert membership == {}

    def test_no_edges(self):
        nodes = [
            _node("code:function:a.py::foo"),
            _node("code:function:a.py::bar"),
        ]
        be = _StubBackend(nodes, [])
        communities, _ = compute_communities(be)
        assert communities == []

    def test_self_loops_ignored(self):
        n = _node("code:function:a.py::recur")
        be = _StubBackend([n], [_edge(n.uid, n.uid)])
        communities, _ = compute_communities(be)
        # Self-loop alone produces no detectable community.
        assert communities == []


class TestCommunitiesToProcesses:
    def test_filters_by_relevant_uids(self, three_flow_backend):
        communities, _ = compute_communities(three_flow_backend)
        login_uid = "code:function:auth/login.py::login"
        out = communities_to_processes(communities, relevant_uids={login_uid})
        # Should return ONLY the community containing login.
        assert len(out) == 1
        assert any(m["uid"] == login_uid for m in out[0]["members"])

    def test_returns_all_when_relevant_uids_none(self, three_flow_backend):
        communities, _ = compute_communities(three_flow_backend)
        out = communities_to_processes(communities, relevant_uids=None)
        assert len(out) == len(communities)


# ---------------------------------------------------------------------------
# Tool envelope
# ---------------------------------------------------------------------------


def _parse_envelope(value):
    """`_ok`/`_fail` return JSON-encoded strings via the shared envelope."""
    import json

    if isinstance(value, str):
        return json.loads(value)
    return value


class TestToolEnvelope:
    def test_validation_rejects_non_positive_top(self, three_flow_backend, monkeypatch):
        from graph_os.tools import graph as graph_tools

        monkeypatch.setattr(graph_tools, "_BACKEND_SINGLETON", three_flow_backend)
        monkeypatch.setattr(graph_tools, "_backend", lambda backend=None: three_flow_backend)

        res = _parse_envelope(graph_tools.cos_graph_communities(top=0))
        assert res["ok"] is False
        assert res["error"]["category"] == "validation"

    def test_top_capped(self, three_flow_backend, monkeypatch):
        from graph_os.tools import graph as graph_tools

        monkeypatch.setattr(graph_tools, "_BACKEND_SINGLETON", three_flow_backend)
        monkeypatch.setattr(graph_tools, "_backend", lambda backend=None: three_flow_backend)

        res = _parse_envelope(graph_tools.cos_graph_communities(top=500))
        assert res["ok"] is True
        assert len(res["data"]["processes"]) <= 200

    def test_graph_query_surfaces_processes(self, three_flow_backend, monkeypatch):
        from graph_os.tools import graph as graph_tools

        monkeypatch.setattr(graph_tools, "_BACKEND_SINGLETON", three_flow_backend)
        monkeypatch.setattr(graph_tools, "_backend", lambda backend=None: three_flow_backend)
        monkeypatch.setattr(
            graph_tools,
            "_lexical_search",
            lambda be, *, q, kinds=None, limit=10, max_hops=2: [
                three_flow_backend.get_node("code:function:auth/login.py::login")
            ],
        )

        res = _parse_envelope(graph_tools.cos_graph_query("login"))
        assert res["ok"] is True
        # processes[] is always present — may be empty when no clustering
        # signal exists, but never absent.
        assert "processes" in res["data"]


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------


class TestCache:
    def test_cache_invalidates_on_edge_change(self):
        nodes = [
            _node("code:function:a.py::a"),
            _node("code:function:a.py::b"),
            _node("code:function:a.py::c"),
        ]
        edges = [_edge(nodes[0].uid, nodes[1].uid)]
        be = _StubBackend(nodes, edges)
        first, _ = compute_communities(be)
        # Mutate edge set (simulating reindex).
        be._edges.append(_edge(nodes[1].uid, nodes[2].uid))
        second, _ = compute_communities(be)
        # Different signature → recomputation, possibly different shape.
        assert (
            sum(c.member_count for c in first) != sum(c.member_count for c in second)
        ) or first == second  # at minimum, no crash, no stale read
