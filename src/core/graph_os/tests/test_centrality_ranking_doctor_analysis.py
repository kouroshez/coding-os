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


def _seed(migrated_conn, monkeypatch, nodes, edges):
    from graph_os.backends.sqlite_backend import SqliteBackend

    be = SqliteBackend(conn=migrated_conn)
    be.bulk_upsert(nodes, edges)
    graph._BACKEND_SINGLETON = be
    monkeypatch.setattr(graph, "_backend", lambda *, backend=None: be)
    return be


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

    def test_type_only_import_loop_is_not_a_cycle(self, migrated_conn, monkeypatch):
        # Type-only imports carry edge_type='imports_type', which the import
        # cycle scan excludes — a loop formed only by them is no runtime cycle.
        nodes = [
            GraphNode(uid="code:module:a", kind="code:module", label="a", file_path="a.py"),
            GraphNode(uid="code:module:b", kind="code:module", label="b", file_path="b.py"),
        ]
        edges = [
            GraphEdge(
                source_uid="code:module:a",
                target_uid="code:module:b",
                edge_type="imports_type",
                extractor="test",
                confidence=0.5,
            ),
            GraphEdge(
                source_uid="code:module:b",
                target_uid="code:module:a",
                edge_type="imports_type",
                extractor="test",
                confidence=0.5,
            ),
        ]
        _seed(migrated_conn, monkeypatch, nodes, edges)
        try:
            data = _ok(graph.cos_graph_cycles(scope="imports"))
            assert data["total_count"] == 0
        finally:
            graph._BACKEND_SINGLETON = None

    def test_acyclic_call_graph_returns_empty(self, seeded):
        data = _ok(graph.cos_graph_cycles(scope="calls"))
        assert data["total_count"] == 0  # foo->bar->baz is a DAG

    def test_rejects_bad_scope(self, seeded):
        _fail(graph.cos_graph_cycles(scope="bogus"), "validation")


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


class TestDiff:
    def test_rejects_injection_ref(self, seeded):
        _fail(graph.cos_graph_diff(base="x; rm -rf /"), "validation")

    def test_same_ref_is_empty(self, seeded):
        # HEAD..HEAD has no changed files → empty blast radius (deterministic).
        data = _ok(graph.cos_graph_diff(base="HEAD", head="HEAD"))
        assert data["file_count"] == 0
        assert data["risk_level"] == "none"


class TestPhantomOrphan:
    def test_task_with_source_line_anchor_is_phantom(self):
        # Code-line ref mis-noded as a task → prunable garbage.
        assert graph._is_phantom_orphan(
            "task", None, "task:file:docs/tasks/notes/src/core/x/graph.py#L2787"
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
        # Patch where the helper is DEFINED — graph.py and _graph_doctor.py both
        # re-export it, so patching either facade leaves _is_phantom_orphan calling
        # its own module-level name. In-function: the sibling imports graph.py.
        from graph_os.tools import _doctor_orphans

        monkeypatch.setattr(_doctor_orphans, "_current_extractor_ids", lambda: frozenset())
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
