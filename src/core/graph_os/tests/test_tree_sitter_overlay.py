"""Tests for tree_sitter_overlay."""

from __future__ import annotations

import pytest

from graph_os import tree_sitter_overlay as ts


def _skip_if_missing(language_id: str) -> None:
    if not ts.is_available():
        pytest.skip("tree-sitter core not installed")
    if ts._load_language(language_id) is None:
        pytest.skip(f"tree-sitter grammar {language_id} not installed")


class TestAvailability:
    def test_is_available(self):
        # We installed the graph_os extra — expect True.
        assert ts.is_available() is True

    def test_unknown_language_returns_none(self):
        assert ts.parse("klingon", "dis iz code") is None


class TestParsing:
    def test_python_parse(self):
        _skip_if_missing("python")
        parsed = ts.parse("python", "def foo():\n    return 1\n")
        assert parsed is not None
        assert parsed.root.type == "module"

    def test_typescript_parse(self):
        _skip_if_missing("typescript")
        parsed = ts.parse("typescript", "export function hi(): number { return 1; }\n")
        assert parsed is not None
        assert parsed.root.type == "program"

    def test_tsx_parse(self):
        _skip_if_missing("tsx")
        parsed = ts.parse("tsx", "export const X = () => <div>hi</div>")
        assert parsed is not None

    def test_bash_parse(self):
        _skip_if_missing("bash")
        parsed = ts.parse("bash", "echo hi\nsource util.sh\n")
        assert parsed is not None

    def test_yaml_parse(self):
        _skip_if_missing("yaml")
        parsed = ts.parse("yaml", "key: value\nnested:\n  inner: 1\n")
        assert parsed is not None


class TestHelpers:
    def test_iter_nodes_filters(self):
        _skip_if_missing("python")
        parsed = ts.parse("python", "def a(): pass\ndef b(): pass\n")
        assert parsed is not None
        fn_nodes = list(ts.iter_nodes(parsed.root, {"function_definition"}))
        assert len(fn_nodes) == 2

    def test_node_text_roundtrip(self):
        _skip_if_missing("python")
        src = "def hello():\n    return 1\n"
        parsed = ts.parse("python", src)
        assert parsed is not None
        fn = next(ts.iter_nodes(parsed.root, {"function_definition"}))
        text = ts.node_text(fn, src.encode("utf-8"))
        assert text.startswith("def hello")

    def test_empty_source_parses(self):
        _skip_if_missing("python")
        parsed = ts.parse("python", "")
        assert parsed is not None
        assert parsed.root.type == "module"


class TestIntegrationWithExtractor:
    def test_code_ts_records_overlay_metadata(self):
        _skip_if_missing("typescript")
        from graph_os.extractors import code_ts

        result = code_ts.extract(
            "frontend/x.ts",
            "import { a } from './b';\nexport function hi() { return a(); }\n",
        )
        modules = [n for n in result.nodes if n.kind == "code:module"]
        assert modules
        meta = modules[0].metadata
        assert "ts_ast_nodes" in meta
        assert meta["ts_ast_nodes"] > 0
        assert meta["ts_language"] in {"typescript", "tsx"}


class TestDegradation:
    def test_load_language_none_when_unavailable(self, monkeypatch):
        # Lean install (tree-sitter absent) → _load_language degrades to None.
        ts._load_language.cache_clear()
        monkeypatch.setattr(ts, "is_available", lambda: False)
        try:
            assert ts._load_language("python") is None
        finally:
            ts._load_language.cache_clear()  # don't poison the lru_cache

    def test_parse_none_when_unavailable(self, monkeypatch):
        ts._load_language.cache_clear()
        monkeypatch.setattr(ts, "is_available", lambda: False)
        try:
            assert ts.parse("python", "x = 1") is None
        finally:
            ts._load_language.cache_clear()


class TestNodeTextEdge:
    def test_node_text_returns_empty_on_bad_node(self):
        # A node-like object without start_byte/end_byte → "" (not a crash).
        assert ts.node_text(object(), b"data") == ""
