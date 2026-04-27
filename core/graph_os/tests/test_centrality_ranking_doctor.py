"""Tests for cos_graph_centrality, cos_graph_ranking, cos_graph_doctor (Wave 1 A4)."""
from __future__ import annotations

import json

import pytest

from graph_os.tools import graph
from graph_os.types import GraphEdge, GraphNode


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def seeded(migrated_conn, monkeypatch):
    """Small seeded graph: foo→bar→baz call chain + orphan node."""
    from graph_os.backends.sqlite_backend import SqliteBackend

    backend = SqliteBackend(conn=migrated_conn)
    graph._BACKEND_SINGLETON = backend
    monkeypatch.setattr(graph, "_backend", lambda *, backend=None: graph._BACKEND_SINGLETON)

    nodes = [
        GraphNode(uid="code:function:a.py::foo", kind="code:function", label="foo", file_path="a.py", start_line=1),
        GraphNode(uid="code:function:a.py::bar", kind="code:function", label="bar", file_path="a.py", start_line=10),
        GraphNode(uid="code:function:a.py::baz", kind="code:function", label="baz", file_path="a.py", start_line=20),
        GraphNode(uid="code:file:a.py", kind="code:file", label="a.py", file_path="a.py"),
        # orphan — no edges
        GraphNode(uid="code:function:b.py::orphan", kind="code:function", label="orphan", file_path="b.py", start_line=1),
    ]
    edges = [
        GraphEdge(source_uid="code:function:a.py::foo", target_uid="code:function:a.py::bar", edge_type="calls", extractor="test", confidence=0.9),
        GraphEdge(source_uid="code:function:a.py::bar", target_uid="code:function:a.py::baz", edge_type="calls", extractor="test", confidence=0.8),
        GraphEdge(source_uid="code:file:a.py", target_uid="code:function:a.py::foo", edge_type="contains", extractor="test", confidence=1.0),
        GraphEdge(source_uid="code:file:a.py", target_uid="code:function:a.py::bar", edge_type="contains", extractor="test", confidence=1.0),
        GraphEdge(source_uid="code:file:a.py", target_uid="code:function:a.py::baz", edge_type="contains", extractor="test", confidence=1.0),
    ]
    backend.bulk_upsert(nodes, edges)
    yield backend
    graph._BACKEND_SINGLETON = None


def _ok(env) -> dict:
    if isinstance(env, str):
        env = json.loads(env)
    assert env["ok"] is True, f"expected ok, got {env}"
    return env["data"]


def _fail(env, category: str) -> None:
    if isinstance(env, str):
        env = json.loads(env)
    assert env["ok"] is False
    assert env["error"]["category"] == category


# ---------------------------------------------------------------------------
# cos_graph_centrality
# ---------------------------------------------------------------------------


class TestCentrality:
    def test_happy_path_returns_nodes(self, seeded):
        data = _ok(graph.cos_graph_centrality())
        assert "nodes" in data
        assert len(data["nodes"]) > 0

    def test_envelope_layer(self, seeded):
        env = graph.cos_graph_centrality()
        if isinstance(env, str):
            env = json.loads(env)
        assert env["data"]["meta"]["layer"] == "graph"

    def test_top_limit(self, seeded):
        data = _ok(graph.cos_graph_centrality(top=2))
        assert len(data["nodes"]) <= 2

    def test_top_validation(self, seeded):
        _fail(graph.cos_graph_centrality(top=-1), "validation")

    def test_metric_validation(self, seeded):
        _fail(graph.cos_graph_centrality(metric="eigenvalue"), "validation")

    def test_kind_filter(self, seeded):
        data = _ok(graph.cos_graph_centrality(kind="code:function"))
        for n in data["nodes"]:
            assert n["kind"] == "code:function"

    def test_scores_sum_bounded(self, seeded):
        data = _ok(graph.cos_graph_centrality())
        for n in data["nodes"]:
            assert 0.0 <= n["centrality_score"] <= 1.0 + 1e-9

    def test_highest_degree_node_is_file(self, seeded):
        # a.py has 3 outbound contains + is target of nothing = 3 out-degree
        # it should rank near the top
        data = _ok(graph.cos_graph_centrality(top=10))
        uids = [n["uid"] for n in data["nodes"]]
        assert "code:file:a.py" in uids

    def test_betweenness_metric_runs(self, seeded):
        data = _ok(graph.cos_graph_centrality(metric="betweenness", top=5))
        assert "nodes" in data
        for n in data["nodes"]:
            assert "centrality_score" in n

    def test_top_cap_at_200(self, seeded):
        data = _ok(graph.cos_graph_centrality(top=999))
        # top is capped at 200
        assert len(data["nodes"]) <= 200


# ---------------------------------------------------------------------------
# cos_graph_ranking
# ---------------------------------------------------------------------------


class TestRanking:
    def test_happy_path(self, seeded):
        data = _ok(graph.cos_graph_ranking())
        assert "nodes" in data
        assert len(data["nodes"]) > 0

    def test_envelope_layer(self, seeded):
        env = graph.cos_graph_ranking()
        if isinstance(env, str):
            env = json.loads(env)
        assert env["data"]["meta"]["layer"] == "graph"

    def test_top_limit(self, seeded):
        data = _ok(graph.cos_graph_ranking(top=2))
        assert len(data["nodes"]) <= 2

    def test_top_validation(self, seeded):
        _fail(graph.cos_graph_ranking(top=0), "validation")

    def test_damping_validation(self, seeded):
        _fail(graph.cos_graph_ranking(damping=1.5), "validation")

    def test_rank_scores_positive(self, seeded):
        data = _ok(graph.cos_graph_ranking())
        for n in data["nodes"]:
            assert n["rank_score"] > 0.0

    def test_personalized_query_filters(self, seeded):
        data = _ok(graph.cos_graph_ranking(query="baz", top=5))
        assert "nodes" in data
        # baz should score relatively high when personalised
        uids = [n["uid"] for n in data["nodes"]]
        assert "code:function:a.py::baz" in uids

    def test_kind_filter_returns_only_that_kind(self, seeded):
        data = _ok(graph.cos_graph_ranking(kind="code:function", top=10))
        for n in data["nodes"]:
            assert n["kind"] == "code:function"

    def test_top_cap_at_200(self, seeded):
        data = _ok(graph.cos_graph_ranking(top=999))
        assert len(data["nodes"]) <= 200

    def test_meta_has_node_count(self, seeded):
        env = graph.cos_graph_ranking()
        if isinstance(env, str):
            env = json.loads(env)
        assert "node_count" in env["data"]["meta"]


# ---------------------------------------------------------------------------
# cos_graph_doctor
# ---------------------------------------------------------------------------


class TestDoctor:
    def test_healthy_graph_no_issues(self, migrated_conn, monkeypatch):
        """Clean graph (no nodes, no edges) = healthy."""
        from graph_os.backends.sqlite_backend import SqliteBackend
        backend = SqliteBackend(conn=migrated_conn)
        graph._BACKEND_SINGLETON = backend
        monkeypatch.setattr(graph, "_backend", lambda *, backend=None: graph._BACKEND_SINGLETON)
        data = _ok(graph.cos_graph_doctor())
        assert data["healthy"] is True
        assert data["issues"] == []
        graph._BACKEND_SINGLETON = None

    def test_envelope_layer(self, seeded):
        env = graph.cos_graph_doctor()
        if isinstance(env, str):
            env = json.loads(env)
        assert env["data"]["meta"]["layer"] == "graph"

    def test_stats_node_edge_count(self, seeded):
        data = _ok(graph.cos_graph_doctor())
        assert data["stats"]["node_count"] >= 5
        assert data["stats"]["edge_count"] >= 5

    def test_orphan_detected(self, seeded, migrated_conn):
        # "orphan" node has no edges — should appear in issues
        data = _ok(graph.cos_graph_doctor())
        categories = {i["category"] for i in data["issues"]}
        assert "orphaned_nodes" in categories

    def test_orphan_count_correct(self, seeded, migrated_conn):
        data = _ok(graph.cos_graph_doctor())
        orphan_issue = next(i for i in data["issues"] if i["category"] == "orphaned_nodes")
        assert orphan_issue["count"] >= 1

    def test_self_loop_detected(self, migrated_conn, monkeypatch):
        """Self-loop edge (source_id == target_id) should appear in issues."""
        from graph_os.backends.sqlite_backend import SqliteBackend
        backend = SqliteBackend(conn=migrated_conn)
        graph._BACKEND_SINGLETON = backend
        monkeypatch.setattr(graph, "_backend", lambda *, backend=None: graph._BACKEND_SINGLETON)
        migrated_conn.execute(
            "INSERT INTO graph_nodes (uid, kind, label, file_path, metadata_json, created_at, updated_at) "
            "VALUES ('code:function:sl.py::loop', 'code:function', 'loop', 'sl.py', '{}', 0, 0)"
        )
        loop_id = migrated_conn.execute(
            "SELECT id FROM graph_nodes WHERE uid='code:function:sl.py::loop'"
        ).fetchone()[0]
        migrated_conn.execute(
            "INSERT INTO graph_edges_v12 (source_id, target_id, edge_type, extractor, "
            "confidence, created_at, updated_at) VALUES (?, ?, 'calls', 'self-loop-extractor', 0.5, 0, 0)",
            (loop_id, loop_id),
        )
        migrated_conn.commit()
        data = _ok(graph.cos_graph_doctor())
        categories = {i["category"] for i in data["issues"]}
        assert "self_loops" in categories
        graph._BACKEND_SINGLETON = None

    def _insert_dangling(self, conn, source_uid: str, source_label: str) -> None:
        """Insert a real source node + an edge to ghost target_id=9999.

        FK enforcement is temporarily disabled so the ghost id passes the
        constraint check — this simulates a row left behind by a failed
        delete or old schema migration.
        """
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute(
            "INSERT OR IGNORE INTO graph_nodes "
            "(uid, kind, label, file_path, metadata_json, created_at, updated_at) "
            "VALUES (?, 'code:function', ?, 'x.py', '{}', 0, 0)",
            (source_uid, source_label),
        )
        src_id = conn.execute(
            "SELECT id FROM graph_nodes WHERE uid=?", (source_uid,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO graph_edges_v12 (source_id, target_id, edge_type, extractor, "
            "confidence, created_at, updated_at) VALUES (?, 9999, 'calls', 'test', 0.9, 0, 0)",
            (src_id,),
        )
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")

    def test_dangling_edge_detected(self, migrated_conn, monkeypatch):
        from graph_os.backends.sqlite_backend import SqliteBackend
        backend = SqliteBackend(conn=migrated_conn)
        graph._BACKEND_SINGLETON = backend
        monkeypatch.setattr(graph, "_backend", lambda *, backend=None: graph._BACKEND_SINGLETON)
        self._insert_dangling(migrated_conn, "code:function:x.py::real", "real")
        data = _ok(graph.cos_graph_doctor())
        categories = {i["category"] for i in data["issues"]}
        assert "dangling_target" in categories
        graph._BACKEND_SINGLETON = None

    def test_fix_flag_clears_dangling(self, migrated_conn, monkeypatch):
        from graph_os.backends.sqlite_backend import SqliteBackend
        backend = SqliteBackend(conn=migrated_conn)
        graph._BACKEND_SINGLETON = backend
        monkeypatch.setattr(graph, "_backend", lambda *, backend=None: graph._BACKEND_SINGLETON)
        self._insert_dangling(migrated_conn, "code:function:z.py::real2", "real2")
        data = _ok(graph.cos_graph_doctor(fix=True))
        assert data["stats"].get("fixed_edge_count", 0) >= 1
        graph._BACKEND_SINGLETON = None

    def test_healthy_true_when_no_issues(self, migrated_conn, monkeypatch):
        """Empty graph = no edges = no dangling, no dupes, no orphans either."""
        from graph_os.backends.sqlite_backend import SqliteBackend
        backend = SqliteBackend(conn=migrated_conn)
        graph._BACKEND_SINGLETON = backend
        monkeypatch.setattr(graph, "_backend", lambda *, backend=None: graph._BACKEND_SINGLETON)
        data = _ok(graph.cos_graph_doctor())
        # Empty graph: zero orphans (no nodes), zero dangling, zero dupes
        assert data["healthy"] is True
        graph._BACKEND_SINGLETON = None
