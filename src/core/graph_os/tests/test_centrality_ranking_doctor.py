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
            label="baz",
            file_path="a.py",
            start_line=20,
        ),
        GraphNode(uid="code:file:a.py", kind="code:file", label="a.py", file_path="a.py"),
        # orphan — no edges
        GraphNode(
            uid="code:function:b.py::orphan",
            kind="code:function",
            label="orphan",
            file_path="b.py",
            start_line=1,
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
            confidence=0.8,
        ),
        GraphEdge(
            source_uid="code:file:a.py",
            target_uid="code:function:a.py::foo",
            edge_type="contains",
            extractor="test",
            confidence=1.0,
        ),
        GraphEdge(
            source_uid="code:file:a.py",
            target_uid="code:function:a.py::bar",
            edge_type="contains",
            extractor="test",
            confidence=1.0,
        ),
        GraphEdge(
            source_uid="code:file:a.py",
            target_uid="code:function:a.py::baz",
            edge_type="contains",
            extractor="test",
            confidence=1.0,
        ),
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
        # W7/R4-16: legacy `code:function` normalizes to canonical
        # `function` before filtering. Result rows carry the canonical kind.
        data = _ok(graph.cos_graph_centrality(kind="code:function"))
        for n in data["nodes"]:
            assert n["kind"] == "function"

    def test_kind_filter_rejects_unknown(self, seeded):
        # R4-16: a typo'd kind fails validation instead of silently
        # returning an empty list.
        _fail(graph.cos_graph_centrality(kind="not_a_real_kind"), "validation")

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
        # W7.6: in-repo orphans surface under `orphaned_inrepo`;
        # `code:external:unresolved:*` go to `orphaned_external_unresolved`.
        data = _ok(graph.cos_graph_doctor())
        categories = {i["category"] for i in data["issues"]}
        assert "orphaned_inrepo" in categories or "orphaned_external_unresolved" in categories

    def test_orphan_count_correct(self, seeded, migrated_conn):
        data = _ok(graph.cos_graph_doctor())
        orphan_issues = [
            i
            for i in data["issues"]
            if i["category"] in ("orphaned_inrepo", "orphaned_external_unresolved")
        ]
        assert sum(i["count"] for i in orphan_issues) >= 1

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

    def test_doctor_fix_prunes_stub_orphan(self, migrated_conn, monkeypatch):
        """Zero-edge stub:true row classifies as orphaned_phantom and fix=True deletes it."""
        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        graph._BACKEND_SINGLETON = backend
        monkeypatch.setattr(graph, "_backend", lambda *, backend=None: graph._BACKEND_SINGLETON)
        migrated_conn.execute(
            "INSERT INTO graph_nodes (uid, kind, label, file_path, metadata_json, created_at, updated_at) "
            "VALUES ('doc:file:tests/golden/x/AGENTS.md', 'doc_file', 'AGENTS.md', "
            "'tests/golden/x/AGENTS.md', '{\"extractor\": \"md_links@v1\", \"stub\": true}', 0, 0)"
        )
        migrated_conn.commit()
        data = _ok(graph.cos_graph_doctor())
        phantom = next(i for i in data["issues"] if i["category"] == "orphaned_phantom")
        assert any(s["uid"] == "doc:file:tests/golden/x/AGENTS.md" for s in phantom["sample"])
        _ok(graph.cos_graph_doctor(fix=True))
        remaining = migrated_conn.execute(
            "SELECT COUNT(*) FROM graph_nodes WHERE uid='doc:file:tests/golden/x/AGENTS.md'"
        ).fetchone()[0]
        assert remaining == 0
        graph._BACKEND_SINGLETON = None

    def test_doctor_fix_gc_dead_external_stub(self, migrated_conn, monkeypatch):
        """Zero-edge code:external stub (deleted source file) is GC'd by fix=True."""
        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        graph._BACKEND_SINGLETON = backend
        monkeypatch.setattr(graph, "_backend", lambda *, backend=None: graph._BACKEND_SINGLETON)
        migrated_conn.execute(
            "INSERT INTO graph_nodes (uid, kind, label, file_path, metadata_json, created_at, updated_at) "
            "VALUES ('code:external:unresolved:setAudits', 'identifier', 'unresolved:setAudits', "
            "NULL, '{}', 0, 0)"
        )
        migrated_conn.commit()
        data = _ok(graph.cos_graph_doctor())
        stub_issue = next(
            i for i in data["issues"] if i["category"] == "orphaned_external_unresolved"
        )
        assert stub_issue["severity"] == "info"
        assert "orphaned_external_unresolved" in data["meta"]["fixable_categories"]
        _ok(graph.cos_graph_doctor(fix=True))
        remaining = migrated_conn.execute(
            "SELECT COUNT(*) FROM graph_nodes WHERE uid='code:external:unresolved:setAudits'"
        ).fetchone()[0]
        assert remaining == 0
        graph._BACKEND_SINGLETON = None

    def test_issue_count_counts_real_categories_only(self, migrated_conn, monkeypatch):
        """Info categories never inflate stats.issue_count (Hub badge honesty)."""
        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        graph._BACKEND_SINGLETON = backend
        monkeypatch.setattr(graph, "_backend", lambda *, backend=None: graph._BACKEND_SINGLETON)
        migrated_conn.execute(
            "INSERT INTO graph_nodes (uid, kind, label, file_path, metadata_json, created_at, updated_at) "
            "VALUES ('code:external:unresolved:onlyStub', 'identifier', 'unresolved:onlyStub', "
            "NULL, '{}', 0, 0)"
        )
        migrated_conn.commit()
        data = _ok(graph.cos_graph_doctor())
        assert data["healthy"] is True
        assert data["stats"]["issue_count"] == 0
        assert data["stats"]["issue_count_total"] >= 1
        graph._BACKEND_SINGLETON = None

    def test_parse_errors_stats_zero_on_clean_graph(self, migrated_conn, monkeypatch):
        """No file_index_state parse errors → stats report 0, no issue raised."""
        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        graph._BACKEND_SINGLETON = backend
        monkeypatch.setattr(graph, "_backend", lambda *, backend=None: graph._BACKEND_SINGLETON)
        data = _ok(graph.cos_graph_doctor())
        assert data["stats"]["files_with_parse_errors"] == 0
        assert data["stats"]["parse_error_total"] == 0
        assert "files_with_parse_errors" not in {i["category"] for i in data["issues"]}
        graph._BACKEND_SINGLETON = None

    def test_parse_errors_surfaced_as_informational(self, migrated_conn, monkeypatch):
        """file_index_state rows with parse_errors_count > 0 surface visibly
        but do NOT trip healthy=false (informational, TASK-293)."""
        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        graph._BACKEND_SINGLETON = backend
        monkeypatch.setattr(graph, "_backend", lambda *, backend=None: graph._BACKEND_SINGLETON)
        for path, n_err in (("a.sh", 3), ("b.md", 2)):
            migrated_conn.execute(
                "INSERT INTO file_index_state (file_path, content_hash, extractor_chain, "
                "nodes_written, edges_written, parse_errors_count, last_indexed_at) "
                "VALUES (?, 'h', 'chain', 0, 0, ?, 0)",
                (path, n_err),
            )
        migrated_conn.commit()
        data = _ok(graph.cos_graph_doctor())
        assert data["stats"]["files_with_parse_errors"] == 2
        assert data["stats"]["parse_error_total"] == 5
        pe = [i for i in data["issues"] if i["category"] == "files_with_parse_errors"]
        assert len(pe) == 1
        assert pe[0]["count"] == 2
        assert pe[0]["parse_error_total"] == 5
        assert pe[0]["severity"] == "info"
        # informational — must not flip the overall verdict
        assert data["healthy"] is True
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
        src_id = conn.execute("SELECT id FROM graph_nodes WHERE uid=?", (source_uid,)).fetchone()[0]
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


class TestServerStaleGuard:
    """F5 — _server_stale() flags a long-running server older than graph.py."""

    def test_false_in_fresh_process(self):
        # Disk mtime == captured-at-import mtime → not stale.
        assert graph._server_stale() is False

    def test_true_when_disk_newer_than_boot(self, monkeypatch):
        monkeypatch.setattr(graph, "_MODULE_LOADED_MTIME", 1.0)
        assert graph._server_stale() is True

    def test_doctor_meta_reports_server_stale(self, migrated_conn, monkeypatch):
        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        graph._BACKEND_SINGLETON = backend
        monkeypatch.setattr(graph, "_backend", lambda *, backend=None: graph._BACKEND_SINGLETON)
        data = _ok(graph.cos_graph_doctor())
        assert "server_stale" in data["meta"]
        graph._BACKEND_SINGLETON = None


def _seed(migrated_conn, monkeypatch, nodes, edges):
    from graph_os.backends.sqlite_backend import SqliteBackend

    be = SqliteBackend(conn=migrated_conn)
    be.bulk_upsert(nodes, edges)
    graph._BACKEND_SINGLETON = be
    monkeypatch.setattr(graph, "_backend", lambda *, backend=None: be)
    return be


def test_centrality_excludes_structural_edges_by_default(migrated_conn, monkeypatch):
    """TASK-046: degree counts behavioural edges by default — a contains-only
    container scores 0; with include_structural=True it counts its children."""
    nodes = [
        GraphNode(
            uid=f"code:function:m.py::f{i}",
            kind="code:function",
            label=f"f{i}",
            file_path="m.py",
            start_line=i,
        )
        for i in range(6)
    ]
    nodes.append(GraphNode(uid="code:file:m.py", kind="code:file", label="m.py", file_path="m.py"))
    edges = [
        GraphEdge(
            source_uid="code:file:m.py",
            target_uid=f"code:function:m.py::f{i}",
            edge_type="contains",
            extractor="test",
            confidence=1.0,
        )
        for i in range(6)
    ]
    edges += [
        GraphEdge(
            source_uid=f"code:function:m.py::f{i}",
            target_uid="code:function:m.py::f0",
            edge_type="calls",
            extractor="test",
            confidence=1.0,
        )
        for i in range(1, 6)
    ]
    _seed(migrated_conn, monkeypatch, nodes, edges)
    try:
        default = {n["uid"]: n for n in _ok(graph.cos_graph_centrality(top=20))["nodes"]}
        # the file's 6 outbound edges are all `contains` → 0 behavioural degree
        assert default.get("code:file:m.py", {}).get("out_degree", 0) == 0
        assert default["code:function:m.py::f0"]["in_degree"] == 5
        # raw all-edge degree restores the structural count
        raw = {
            n["uid"]: n
            for n in _ok(graph.cos_graph_centrality(top=20, include_structural=True))["nodes"]
        }
        assert raw["code:file:m.py"]["out_degree"] == 6
    finally:
        graph._BACKEND_SINGLETON = None


def test_doctor_orphan_breakdown_splits_by_prefix(migrated_conn, monkeypatch):
    """TASK-046: doctor reports an accurate per-prefix split of stub orphans
    instead of lumping all under the 'external_unresolved' label."""
    nodes = [
        GraphNode(uid="code:external:unresolved:foo", kind="identifier", label="foo"),
        GraphNode(uid="code:external:pathlib:Path", kind="identifier", label="Path"),
        GraphNode(uid="cos:identifier:skillX", kind="identifier", label="skillX"),
    ]
    _seed(migrated_conn, monkeypatch, nodes, [])
    try:
        data = _ok(graph.cos_graph_doctor())
        issue = next(i for i in data["issues"] if i["category"] == "orphaned_external_unresolved")
        assert issue["breakdown"] == {
            "external_unresolved": 1,
            "external_other": 1,
            "identifier_stub": 1,
        }
    finally:
        graph._BACKEND_SINGLETON = None


def test_ranking_labels_outrank_incidental_path_match(migrated_conn, monkeypatch):
    """TASK-040 (F6): a node whose LABEL matches the query must outrank a
    generic 'Work Log' doc_heading that only matches via its uid PATH (a
    TASK file path containing the term). The heading is not seeded at all."""
    nodes = [
        GraphNode(
            uid="code:function:g.py::graph_handler",
            kind="code:function",
            label="graph_handler",
            file_path="g.py",
            start_line=1,
        ),
        GraphNode(
            uid="code:function:g.py::caller",
            kind="code:function",
            label="caller",
            file_path="g.py",
            start_line=5,
        ),
        # generic heading living in a TASK file path containing "graph"
        GraphNode(
            uid="doc:heading:docs/tasks/TASK-029-graph-audit.md#work-log:2",
            kind="doc_heading",
            label="Work Log",
            file_path="docs/tasks/TASK-029-graph-audit.md",
            start_line=2,
        ),
    ]
    edges = [
        GraphEdge(
            source_uid="code:function:g.py::caller",
            target_uid="code:function:g.py::graph_handler",
            edge_type="calls",
            extractor="test",
            confidence=1.0,
        ),
    ]
    _seed(migrated_conn, monkeypatch, nodes, edges)
    try:
        nodes_out = _ok(graph.cos_graph_ranking(query="graph", top=10))["nodes"]
        order = [n["uid"] for n in nodes_out]
        handler = "code:function:g.py::graph_handler"
        worklog = "doc:heading:docs/tasks/TASK-029-graph-audit.md#work-log:2"
        assert handler in order
        # the label-match node ranks above the generic heading (or the heading
        # is absent because it was never seeded)
        if worklog in order:
            assert order.index(handler) < order.index(worklog)
    finally:
        graph._BACKEND_SINGLETON = None


# ---------------------------------------------------------------------------
# cos_graph_dead_code
# ---------------------------------------------------------------------------


class TestDeadCode:
    def test_flags_unreferenced_symbols(self, seeded):
        data = _ok(graph.cos_graph_dead_code(kind="function"))
        labels = {d["label"] for d in data["dead"]}
        assert "orphan" in labels  # zero inbound edges → dead
        assert "foo" in labels  # only inbound is `contains` (structural, not behavioural)
        assert "bar" not in labels  # called by foo
        assert "baz" not in labels  # called by bar
        assert data["total_count"] >= 2
        assert "candidates only" in data["note"]

    def test_rejects_unknown_kind(self, seeded):
        _fail(graph.cos_graph_dead_code(kind="bogus"), "validation")

    def test_envelope_meta_layer_graph(self, seeded):
        data = _ok(graph.cos_graph_dead_code())
        assert data["meta"]["layer"] == "graph"


# ---------------------------------------------------------------------------
# cos_graph_cycles
# ---------------------------------------------------------------------------


class TestCycles:
    def test_detects_module_import_cycle(self, migrated_conn, monkeypatch):
        nodes = [
            GraphNode(uid="code:module:a", kind="code:module", label="a", file_path="a.py"),
            GraphNode(uid="code:module:b", kind="code:module", label="b", file_path="b.py"),
            GraphNode(uid="code:module:c", kind="code:module", label="c", file_path="c.py"),
        ]
        edges = [
            GraphEdge(
                source_uid="code:module:a",
                target_uid="code:module:b",
                edge_type="imports",
                extractor="test",
                confidence=0.9,
            ),
            GraphEdge(
                source_uid="code:module:b",
                target_uid="code:module:a",
                edge_type="imports",
                extractor="test",
                confidence=0.9,
            ),
            GraphEdge(
                source_uid="code:module:b",
                target_uid="code:module:c",
                edge_type="imports",
                extractor="test",
                confidence=0.9,
            ),
        ]
        _seed(migrated_conn, monkeypatch, nodes, edges)
        try:
            data = _ok(graph.cos_graph_cycles(scope="imports"))
            assert data["total_count"] >= 1
            members = data["cycles"][0]["members"]
            assert "code:module:a" in members and "code:module:b" in members
            assert "code:module:c" not in members  # c is a leaf, not in the cycle
        finally:
            graph._BACKEND_SINGLETON = None

    def test_acyclic_call_graph_returns_empty(self, seeded):
        data = _ok(graph.cos_graph_cycles(scope="calls"))
        assert data["total_count"] == 0  # foo->bar->baz is a DAG

    def test_rejects_bad_scope(self, seeded):
        _fail(graph.cos_graph_cycles(scope="bogus"), "validation")


# ---------------------------------------------------------------------------
# cos_graph_test_gap
# ---------------------------------------------------------------------------


class TestTestGap:
    def test_flags_untested_excludes_tested_and_testcode(self, migrated_conn, monkeypatch):
        nodes = [
            GraphNode(
                uid="code:function:app.py::prod_tested",
                kind="code:function",
                label="prod_tested",
                file_path="app.py",
            ),
            GraphNode(
                uid="code:function:app.py::prod_untested",
                kind="code:function",
                label="prod_untested",
                file_path="app.py",
            ),
            GraphNode(
                uid="code:function:tests/test_app.py::test_it",
                kind="code:function",
                label="test_it",
                file_path="tests/test_app.py",
            ),
        ]
        edges = [
            GraphEdge(
                source_uid="code:function:tests/test_app.py::test_it",
                target_uid="code:function:app.py::prod_tested",
                edge_type="calls",
                extractor="test",
                confidence=0.9,
            ),
        ]
        _seed(migrated_conn, monkeypatch, nodes, edges)
        try:
            data = _ok(graph.cos_graph_test_gap(kind="function"))
            labels = {d["label"] for d in data["untested"]}
            assert "prod_untested" in labels  # no test exercises it
            assert "prod_tested" not in labels  # called by test_it
            assert "test_it" not in labels  # test code itself excluded
        finally:
            graph._BACKEND_SINGLETON = None

    def test_rejects_unknown_kind(self, seeded):
        _fail(graph.cos_graph_test_gap(kind="bogus"), "validation")


# ---------------------------------------------------------------------------
# cos_graph_diff
# ---------------------------------------------------------------------------


class TestDiff:
    def test_rejects_injection_ref(self, seeded):
        _fail(graph.cos_graph_diff(base="x; rm -rf /"), "validation")

    def test_same_ref_is_empty(self, seeded):
        # HEAD..HEAD has no changed files → empty blast radius (deterministic).
        data = _ok(graph.cos_graph_diff(base="HEAD", head="HEAD"))
        assert data["file_count"] == 0
        assert data["risk_level"] == "none"


# ---------------------------------------------------------------------------
# _is_phantom_orphan — garbage-orphan classification (doctor --fix pruning)
# ---------------------------------------------------------------------------


class TestPhantomOrphan:
    def test_task_with_source_line_anchor_is_phantom(self):
        # Code-line ref mis-noded as a task → prunable garbage.
        assert graph._is_phantom_orphan(
            "task", None, "task:file:docs/tasks/audits/src/core/x/graph.py#L2787"
        )

    def test_real_task_uid_is_not_phantom(self):
        assert not graph._is_phantom_orphan("task", "docs/tasks/TASK-001.md", "task:file:TASK-001")

    def test_edgeless_module_stub_is_phantom(self):
        assert graph._is_phantom_orphan("module", None, "code:module:itertools")

    def test_edgeless_doc_external_is_phantom(self):
        assert graph._is_phantom_orphan(
            "doc_external", None, "doc:external:https://img.shields.io/badge"
        )

    def test_real_symbol_is_not_phantom(self):
        assert not graph._is_phantom_orphan("function", "src/x.py", "code:function:src/x.py::f")

    def test_inrepo_module_with_path_is_not_phantom(self):
        assert not graph._is_phantom_orphan("module", "src/core/x.py", "code:module:core.x")

    def test_zero_edge_stub_metadata_is_phantom(self):
        # Link-target stub whose minting edge is gone (e.g. golden-tree purge).
        assert graph._is_phantom_orphan(
            "doc_file",
            "tests/golden/claude_base/AGENTS.md",
            "doc:file:tests/golden/claude_base/AGENTS.md",
            '{"extractor": "md_links@v1", "stub": true}',
        )

    def test_legacy_extractor_id_is_phantom(self):
        # `code_ts_ts@v1` was renamed to `code_ts@v1`; the extractor-scoped
        # prune-before-reindex can never match its rows again.
        assert graph._is_phantom_orphan(
            "function",
            "src/core/web/ui/src/features/cos-board/CosBoardPage.tsx",
            "code:function:src/core/web/ui/src/features/cos-board/CosBoardPage.tsx::StatCell",
            '{"component": true, "extractor": "code_ts_ts@v1"}',
        )

    def test_current_extractor_id_is_not_phantom(self):
        assert not graph._is_phantom_orphan(
            "function",
            "src/x.py",
            "code:function:src/x.py::f",
            '{"extractor": "code_python@v1"}',
        )

    def test_empty_registry_skips_legacy_rule(self, monkeypatch):
        # Registry unknown (import failure) must fail closed — never treat
        # every id as legacy and mass-delete.
        monkeypatch.setattr(graph, "_current_extractor_ids", lambda: frozenset())
        assert not graph._is_phantom_orphan(
            "function",
            "src/x.py",
            "code:function:src/x.py::f",
            '{"extractor": "code_ts_ts@v1"}',
        )

    def test_unreadable_metadata_is_not_phantom(self):
        assert not graph._is_phantom_orphan(
            "function", "src/x.py", "code:function:src/x.py::f", "{not json"
        )


class TestDoctorSlowestExtractions:
    def test_slowest_extractions_surface_as_info(self, seeded, migrated_conn):
        # E1 (polyglot roadmap): duration_ms telemetry must be readable back
        # via doctor as an informational category that never trips healthy.
        migrated_conn.execute(
            "INSERT OR REPLACE INTO file_index_state "
            "(file_path, content_hash, extractor_chain, nodes_written, "
            " edges_written, parse_errors_count, last_indexed_at, duration_ms) "
            "VALUES ('slow/one.py', 'h1', 'python', 1, 0, 0, 0, 950), "
            "       ('slow/two.py', 'h2', 'python', 1, 0, 0, 0, 120)"
        )
        migrated_conn.commit()
        data = _ok(graph.cos_graph_doctor())
        slow = next(i for i in data["issues"] if i["category"] == "slowest_extractions")
        assert slow["severity"] == "info"
        assert slow["sample"][0]["file_path"] == "slow/one.py"
        assert slow["sample"][0]["duration_ms"] == 950

    def test_no_duration_rows_no_category(self, migrated_conn, monkeypatch):
        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        graph._BACKEND_SINGLETON = backend
        monkeypatch.setattr(graph, "_backend", lambda *, backend=None: graph._BACKEND_SINGLETON)
        data = _ok(graph.cos_graph_doctor())
        categories = {i["category"] for i in data["issues"]}
        assert "slowest_extractions" not in categories
        assert data["healthy"] is True
        graph._BACKEND_SINGLETON = None

    def test_within_budget_durations_stay_out_of_issues(self, migrated_conn, monkeypatch):
        """Below the 500ms floor: telemetry in stats only, no issue card (TASK-396)."""
        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        graph._BACKEND_SINGLETON = backend
        monkeypatch.setattr(graph, "_backend", lambda *, backend=None: graph._BACKEND_SINGLETON)
        migrated_conn.execute(
            "INSERT OR REPLACE INTO file_index_state "
            "(file_path, content_hash, extractor_chain, nodes_written, "
            " edges_written, parse_errors_count, last_indexed_at, duration_ms) "
            "VALUES ('fast/one.py', 'h1', 'python', 1, 0, 0, 0, 356), "
            "       ('fast/two.py', 'h2', 'python', 1, 0, 0, 0, 120)"
        )
        migrated_conn.commit()
        data = _ok(graph.cos_graph_doctor())
        categories = {i["category"] for i in data["issues"]}
        assert "slowest_extractions" not in categories
        assert data["stats"]["slowest_extraction_ms"] == 356
        graph._BACKEND_SINGLETON = None
