"""Tests for graph_os.entry_points (TASK-081)."""
from __future__ import annotations

import pytest

from graph_os import entry_points
from graph_os.types import GraphNode


class _StubBackend:
    """Minimal GraphBackend stub — only sample_nodes + close used here."""

    backend_id = "stub"

    def __init__(self, nodes: list[GraphNode]):
        self._nodes = nodes

    def sample_nodes(self, kind, limit):
        return [n for n in self._nodes if (kind is None or n.kind == kind)][:limit]

    def close(self):  # pragma: no cover
        pass


def _node(uid, kind, label, file_path=None, signature=None, start_line=1):
    return GraphNode(
        uid=uid, kind=kind, label=label, file_path=file_path,
        start_line=start_line, signature=signature,
    )


def test_main_signal_label_exact():
    be = _StubBackend([_node("u:m", "function", "main", "src/app.py")])
    eps = entry_points.discover(be, min_score=0.0)
    assert any(e.kind == "main" and "label_exact" in e.components for e in eps)


def test_main_signal_path_main_py():
    be = _StubBackend([_node("u:m2", "function", "run", "pkg/main.py")])
    eps = entry_points.discover(be, min_score=0.0)
    main_eps = [e for e in eps if e.kind == "main"]
    assert main_eps, "expected at least one main-kind ep"
    assert "path_main" in main_eps[0].components


def test_cli_signal_path_cli():
    be = _StubBackend([_node("u:cli", "function", "command_create", "cli/board.py")])
    eps = entry_points.discover(be, min_score=0.0, kind_filter="cli")
    assert eps and "path_cli" in eps[0].components


def test_http_route_kind_dominates():
    be = _StubBackend([_node("u:r", "route", "GET /api/x", "core/web/routes/x.py")])
    eps = entry_points.discover(be, min_score=0.0, kind_filter="http")
    assert eps and eps[0].score >= 0.55  # kind_route base


def test_test_signal_path_and_label():
    be = _StubBackend([_node("u:t", "function", "test_fn", "tests/test_x.py")])
    eps = entry_points.discover(be, min_score=0.0, kind_filter="test")
    assert eps and {"path_tests", "label_test_prefix"}.issubset(set(eps[0].components))


def test_cron_signal():
    be = _StubBackend([_node("u:c", "function", "cron_tick", "jobs/sweep.py")])
    eps = entry_points.discover(be, min_score=0.0, kind_filter="cron")
    assert eps and eps[0].score >= 0.45


def test_min_score_filters_low():
    # weak signal — score < 0.10
    be = _StubBackend([_node("u:weak", "function", "anything", "src/x.py")])
    eps = entry_points.discover(be, min_score=0.5)
    assert eps == []


def test_invalid_kind_filter_raises():
    be = _StubBackend([])
    with pytest.raises(ValueError, match="kind_filter must be one of"):
        entry_points.discover(be, kind_filter="bogus")


def test_to_dict_shape():
    be = _StubBackend([_node("u:r2", "route", "POST /api/y", "core/web/routes/y.py")])
    eps = entry_points.discover(be, min_score=0.0, kind_filter="http")
    d = eps[0].to_dict()
    assert set(d.keys()) == {"uid", "kind", "score", "label", "file_path", "start_line", "components"}
    assert isinstance(d["components"], list)


def test_sort_stable_by_score_then_uid():
    n1 = _node("u:a", "function", "main", "a/main.py")  # score = 0.45+0.20 = 0.65
    n2 = _node("u:b", "function", "main", "b/main.py")  # same score
    be = _StubBackend([n2, n1])
    eps = entry_points.discover(be, min_score=0.0, kind_filter="main")
    assert [e.uid for e in eps] == ["u:a", "u:b"]


def test_sample_nodes_failure_swallowed():
    class Broken:
        backend_id = "broken"
        def sample_nodes(self, kind, limit):
            raise RuntimeError("boom")
        def close(self):  # pragma: no cover
            pass
    eps = entry_points.discover(Broken(), min_score=0.0)
    assert eps == []
