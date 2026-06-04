"""Core extraction tests for code_php (tree-sitter-php path)."""

from __future__ import annotations

from graph_os.extractors import code_php as p


def _ex(src, path="app/Foo.php"):
    return p.extract(path, src)


def _labels(r, kind):
    return {n.label for n in r.nodes if n.kind == kind}


def _edges(r, et):
    return [
        (e.source_uid.split("::")[-1], e.target_uid.split("::")[-1])
        for e in r.edges
        if e.edge_type == et
    ]


def _targets(r, et):
    return [e.target_uid for e in r.edges if e.edge_type == et]


class TestDeclarations:
    def test_class_interface_trait(self):
        r = _ex("<?php\nclass C {}\ninterface I {}\ntrait T {}")
        assert {"C", "T"} <= _labels(r, "code:class")
        assert "I" in _labels(r, "code:interface")
        assert any(n.label == "T" and n.metadata.get("php_kind") == "trait" for n in r.nodes)

    def test_method_and_function(self):
        r = _ex("<?php\nclass C { public function m() {} }\nfunction f() {}")
        assert "m" in _labels(r, "code:method")
        assert "f" in _labels(r, "code:function")

    def test_property_and_const(self):
        r = _ex("<?php\nclass C { public int $x = 1; const K = 2; }")
        assert "x" in _labels(r, "code:variable")
        assert "K" in _labels(r, "code:variable")

    def test_namespace_module_label(self):
        r = _ex("<?php\nnamespace App\\Http;\nclass C {}")
        mod = next(n for n in r.nodes if n.kind == "code:module")
        assert mod.label == "App\\Http"


class TestImports:
    def test_use_import_edge(self):
        r = _ex("<?php\nuse App\\Models\\User;\nclass C {}")
        assert any(t.endswith("App\\Models\\User") for t in _targets(r, "imports"))

    def test_grouped_use(self):
        r = _ex("<?php\nuse App\\Lib\\{A, B as C};\nclass X {}")
        tgts = _targets(r, "imports")
        assert any(t.endswith("App\\Lib\\A") for t in tgts)
        assert any(t.endswith("App\\Lib\\B") for t in tgts)


class TestHeritage:
    def test_extends_external(self):
        r = _ex("<?php\nclass C extends Core {}")
        assert any("Core" in t for _, t in _edges(r, "inherits_from"))

    def test_implements_local_interface(self):
        r = _ex("<?php\ninterface I {}\nclass C implements I {}")
        assert ("C", "I") in _edges(r, "implements")  # resolved to the local interface

    def test_use_trait_inherits(self):
        r = _ex("<?php\ntrait T {}\nclass C { use T; }")
        assert ("C", "T") in _edges(r, "inherits_from")


class TestTypesAndAttrs:
    def test_typed_property_field_of_type(self):
        r = _ex("<?php\nclass User {}\nclass C { private User $u; }")
        assert any(t == "User" for _, t in _edges(r, "field_of_type"))

    def test_param_and_return_type_resolve_local(self):
        r = _ex("<?php\nclass User {}\nfunction f(User $u): User { return $u; }")
        assert any(t == "User" for _, t in _edges(r, "has_param_type"))
        assert any(t == "User" for _, t in _edges(r, "returns_type"))

    def test_primitive_types_skipped(self):
        r = _ex("<?php\nfunction f(int $n): string { return ''; }")
        assert _edges(r, "has_param_type") == []
        assert _edges(r, "returns_type") == []

    def test_attribute_is_decorated_by(self):
        r = _ex('<?php\n#[Route("/x")]\nclass C {}')
        assert any("Route" in t for _, t in _edges(r, "is_decorated_by"))
