"""Tests for I.13 bench harness — runs ≤ 1k files, regression gate.

The 500k-file measurement lives in `scripts/` and `docs/benchmarks/`;
here we only smoke the plumbing so CI stays fast.
"""

from __future__ import annotations

import pytest

from graph_os.bench import BenchResult, build_mixed_corpus, build_python_corpus, run_benchmark
from graph_os.bench.harness import assert_within_budget


class TestFixtures:
    def test_python_corpus_generates_files(self, tmp_path):
        paths = build_python_corpus(tmp_path, count=5)
        assert len(paths) == 5
        # Files are well-formed Python.
        import ast

        for p in paths:
            ast.parse(p.read_text(encoding="utf-8"))

    def test_python_corpus_deterministic(self, tmp_path):
        first = [p.read_text() for p in build_python_corpus(tmp_path / "a", count=3)]
        second = [p.read_text() for p in build_python_corpus(tmp_path / "b", count=3)]
        assert first == second

    def test_mixed_corpus_has_docs_and_routes(self, tmp_path):
        paths = build_mixed_corpus(tmp_path, size=4)
        suffixes = {p.suffix for p in paths}
        assert suffixes == {".md", ".py"}


class TestHarness:
    def test_run_benchmark_returns_result(self, migrated_conn, tmp_path):
        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        paths = build_python_corpus(tmp_path / "corpus", count=5)
        result = run_benchmark(backend, paths)
        assert isinstance(result, BenchResult)
        assert result.corpus_size == 5
        assert result.nodes_written > 0
        assert result.backend_id == "sqlite"

    def test_budget_assertion(self, migrated_conn, tmp_path):
        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        paths = build_python_corpus(tmp_path / "corpus", count=5)
        result = run_benchmark(backend, paths)
        # Very generous budget — this must always pass in CI.
        assert_within_budget(result, per_file_budget_ms=500.0, per_query_budget_ms=500.0)

    def test_budget_fails_when_exceeded(self, migrated_conn, tmp_path):
        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        paths = build_python_corpus(tmp_path / "corpus", count=5)
        result = run_benchmark(backend, paths)
        with pytest.raises(AssertionError):
            assert_within_budget(result, per_file_budget_ms=0.0001, per_query_budget_ms=0.0001)

    def test_result_serialisable(self, migrated_conn, tmp_path):
        import json

        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        paths = build_python_corpus(tmp_path / "corpus", count=3)
        result = run_benchmark(backend, paths)
        json.dumps(result.to_dict())
