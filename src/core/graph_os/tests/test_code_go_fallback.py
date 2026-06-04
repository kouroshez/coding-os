"""Tests for graph_os.extractors.code_go — regex fallback + receiver/test helpers.

The tree-sitter path is covered by test_code_go.py; this forces the
grammar-absent regex fallback (_walk_regex / _emit_regex_import) used on
lean installs, plus the pure _parse_receiver / _classify_test_func logic.
"""

from __future__ import annotations

import textwrap

import pytest

from graph_os.extractors import code_go


@pytest.fixture
def regex_mode(monkeypatch):
    monkeypatch.setattr(code_go, "_TS_AVAILABLE", False)


def _extract(src: str, *, path: str = "pkg/server.go"):
    return code_go.extract(path, textwrap.dedent(src).lstrip("\n"))


# ---------------------------------------------------------------------------
# Regex fallback walker
# ---------------------------------------------------------------------------


class TestRegexFallback:
    def test_package_and_func(self, regex_mode):
        r = _extract("package server\n\nfunc Start() {}\n")
        fns = [n for n in r.nodes if n.kind == "code:function"]
        assert any(n.label == "Start" for n in fns)
        # package name flows into the module label.
        assert any(n.kind == "code:module" and n.label == "server" for n in r.nodes)

    def test_method_receiver(self, regex_mode):
        r = _extract(
            """
            package server
            func (s *Server) Handle() {}
            """
        )
        methods = [n for n in r.nodes if n.kind == "code:method"]
        assert any(n.label == "Server.Handle" for n in methods)

    def test_generic_method_receiver_strips_type_params(self, regex_mode):
        r = _extract(
            """
            package c
            func (c *Container[K, V]) Get() {}
            """
        )
        assert any(n.kind == "code:method" and n.label == "Container.Get" for n in r.nodes)

    def test_type_struct_is_class(self, regex_mode):
        r = _extract("package m\ntype Widget struct {}\n")
        assert any(n.kind == "code:class" and n.label == "Widget" for n in r.nodes)

    def test_type_interface_is_class(self, regex_mode):
        r = _extract("package m\ntype Reader interface {}\n")
        assert any(n.kind == "code:class" and n.label == "Reader" for n in r.nodes)

    def test_single_import(self, regex_mode):
        r = _extract('package m\nimport "fmt"\n')
        assert any(
            e.edge_type == "imports" and e.target_uid == "code:external:fmt" for e in r.edges
        )

    def test_import_block_with_alias_blank_dot(self, regex_mode):
        r = _extract(
            """
            package m
            import (
                "fmt"
                alias "x/y/z"
                _ "side/effect"
                . "dot/pkg"
            )
            """
        )
        ext = {n.label: n for n in r.nodes if n.kind == "code:external"}
        assert "fmt" in ext and "x/y/z" in ext
        assert ext["x/y/z"].metadata.get("alias") == "alias"
        assert ext["side/effect"].metadata.get("blank_import") is True
        assert ext["dot/pkg"].metadata.get("dot_import") is True

    def test_dotted_call_emits_edge(self, regex_mode):
        r = _extract(
            """
            package m
            func run() { db.Query() }
            """
        )
        assert any(e.edge_type == "calls" for e in r.edges)

    def test_init_func_metadata(self, regex_mode):
        r = _extract("package m\nfunc init() {}\n")
        init = [n for n in r.nodes if n.kind == "code:function" and n.label == "init"]
        assert init and init[0].metadata.get("init") is True

    def test_test_func_classified(self, regex_mode):
        r = _extract(
            "package m\nfunc TestThing(t *testing.T) {}\n",
            path="pkg/server_test.go",
        )
        fn = [n for n in r.nodes if n.label == "TestThing"]
        assert fn and fn[0].metadata.get("test_kind") == "test"

    def test_file_and_module_always(self, regex_mode):
        r = _extract("package solo\n")
        assert any(n.kind == "code:file" for n in r.nodes)
        assert any(n.kind == "code:module" for n in r.nodes)


# ---------------------------------------------------------------------------
# _parse_receiver — pure
# ---------------------------------------------------------------------------


class TestParseReceiver:
    def test_pointer_named(self):
        assert code_go._parse_receiver("s *Server") == "Server"

    def test_value_named(self):
        assert code_go._parse_receiver("r Reader") == "Reader"

    def test_pointer_anonymous(self):
        assert code_go._parse_receiver("*Server") == "Server"

    def test_generic_single(self):
        assert code_go._parse_receiver("s *T[int]") == "T"

    def test_generic_multi(self):
        assert code_go._parse_receiver("c *Container[K, V]") == "Container"

    def test_empty(self):
        assert code_go._parse_receiver("") == ""


# ---------------------------------------------------------------------------
# _classify_test_func — pure
# ---------------------------------------------------------------------------


class TestClassifyTestFunc:
    def test_non_test_file_is_none(self):
        assert code_go._classify_test_func("TestX", "pkg/server.go") is None

    def test_test_prefix(self):
        assert code_go._classify_test_func("TestX", "pkg/server_test.go") == "test"

    def test_benchmark(self):
        assert code_go._classify_test_func("BenchmarkX", "x_test.go") == "benchmark"

    def test_example(self):
        assert code_go._classify_test_func("ExampleX", "x_test.go") == "example"

    def test_fuzz(self):
        assert code_go._classify_test_func("FuzzX", "x_test.go") == "fuzz"

    def test_test_main(self):
        assert code_go._classify_test_func("TestMain", "x_test.go") == "test_main"

    def test_lowercase_continuation_not_a_test(self):
        # "Testify" — char after "Test" is lowercase → not a Go test func.
        assert code_go._classify_test_func("Testify", "x_test.go") is None
