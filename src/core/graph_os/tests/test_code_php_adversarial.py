"""Adversarial correctness tests for code_php — same-scope resolution, type exprs.

Locks the tricky-but-correct PHP shapes most likely to silently mis-extract:
$this->/self::/static::/Class:: call resolution, new (local + imported),
nullable/union types, constructor property promotion, recursion self-loop.
"""

from __future__ import annotations

from graph_os.extractors import code_php as p


def _ex(src, path="app/Foo.php"):
    return p.extract(path, src)


def _edges(r, et):
    return [
        (e.source_uid.split("::")[-1], e.target_uid.split("::")[-1])
        for e in r.edges
        if e.edge_type == et
    ]


class TestSameScopeCalls:
    def test_bare_function_call(self):
        r = _ex("<?php\nfunction a(){ b(); }\nfunction b(){}")
        assert ("a", "b") in _edges(r, "calls")

    def test_forward_reference(self):
        r = _ex("<?php\nfunction a(){ later(); }\nfunction later(){}")
        assert ("a", "later") in _edges(r, "calls")

    def test_this_method_call(self):
        r = _ex("<?php\nclass C { function run(){ $this->help(); } function help(){} }")
        assert ("C.run", "C.help") in _edges(r, "calls")

    def test_self_and_static_call(self):
        r = _ex(
            "<?php\nclass C { function run(){ self::s(); static::t(); }"
            " static function s(){} static function t(){} }"
        )
        assert ("C.run", "C.s") in _edges(r, "calls")
        assert ("C.run", "C.t") in _edges(r, "calls")

    def test_class_scoped_call(self):
        r = _ex(
            "<?php\nclass C { static function s(){} }\n"
            "class D { function run(){ C::s(); } }"
        )
        assert ("D.run", "C.s") in _edges(r, "calls")

    def test_recursive_self_call_no_loop(self):
        r = _ex("<?php\nfunction a(){ a(); }")
        assert ("a", "a") not in _edges(r, "calls")


class TestConstructs:
    def test_new_local_class(self):
        r = _ex("<?php\nclass User {}\nclass C { function run(){ $x = new User(); } }")
        assert ("C.run", "User") in _edges(r, "constructs")

    def test_new_imported_class(self):
        r = _ex(
            "<?php\nuse App\\Models\\User;\n"
            "class C { function run(){ $x = new User(); } }"
        )
        assert any("User" in t for _, t in _edges(r, "constructs"))


class TestTypeExpressions:
    def test_nullable_type(self):
        r = _ex("<?php\nclass U {}\nfunction f(?U $u){}")
        assert any(t == "U" for _, t in _edges(r, "has_param_type"))

    def test_union_type(self):
        r = _ex("<?php\nclass A {}\nclass B {}\nfunction f(A|B $x){}")
        names = {t for _, t in _edges(r, "has_param_type")}
        assert {"A", "B"} <= names

    def test_constructor_property_promotion(self):
        r = _ex("<?php\nclass U {}\nclass C { function __construct(private U $u){} }")
        assert any(t == "U" for _, t in _edges(r, "field_of_type"))


class TestRobustness:
    def test_mixed_html_php_no_crash(self):
        r = _ex("<html><body><?php class C {} ?></body></html>", path="t/page.php")
        assert any(n.label == "C" for n in r.nodes if n.kind == "code:class")

    def test_plain_html_file_only_file_node(self):
        r = _ex("<html><body>hi</body></html>", path="t/static.php")
        assert any(n.kind == "code:file" for n in r.nodes)
        assert r.parse_errors == [] or all(pe.kind != "fatal" for pe in r.parse_errors)
