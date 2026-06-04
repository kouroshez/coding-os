"""Regex-fallback tests for code_php (tree-sitter-php absent / lean install)."""

from __future__ import annotations

import pytest

from graph_os.extractors import code_php


@pytest.fixture
def regex_mode(monkeypatch):
    monkeypatch.setattr(code_php, "_TS_AVAILABLE", False)


def _ex(src, path="app/Foo.php"):
    return code_php.extract(path, src)


def _labels(r, kind):
    return {n.label for n in r.nodes if n.kind == kind}


class TestRegexFallback:
    def test_class_and_function(self, regex_mode):
        r = _ex("<?php\nnamespace App;\nclass C {}\nfunction f() {}")
        assert "C" in _labels(r, "code:class")
        assert "f" in _labels(r, "code:function")

    def test_interface_and_trait(self, regex_mode):
        r = _ex("<?php\ninterface I {}\ntrait T {}")
        assert "I" in _labels(r, "code:interface")
        assert any(
            n.label == "T" and n.metadata.get("php_kind") == "trait" for n in r.nodes
        )

    def test_use_import_edge(self, regex_mode):
        r = _ex("<?php\nuse App\\Models\\User;")
        assert any(e.edge_type == "imports" for e in r.edges)

    def test_namespace_module_label(self, regex_mode):
        r = _ex("<?php\nnamespace App\\Http;\nclass C {}")
        mod = next(n for n in r.nodes if n.kind == "code:module")
        assert mod.label == "App\\Http"

    def test_empty_file_no_crash(self, regex_mode):
        r = _ex("<?php\n")
        assert any(n.kind == "code:file" for n in r.nodes)

    def test_abstract_final_class(self, regex_mode):
        r = _ex("<?php\nabstract class A {}\nfinal class B {}")
        assert {"A", "B"} <= _labels(r, "code:class")
