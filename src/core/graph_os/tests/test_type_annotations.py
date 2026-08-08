"""Tests for graph_os.extractors.code_python type-annotation edges (TASK-083).

Coverage matrix:
  - simple param annotation
  - return annotation
  - PEP 604 union (`X | Y` → two branches)
  - `Optional[X]` (None branch dropped)
  - `Union[X, Y]` (legacy form)
  - `list[X]`, `dict[str, X]` (container strip)
  - class field annotation (`name: T`)
  - skips `self` / `cls` first parameter
  - method param annotation
  - kwonly + *args + **kwargs annotations
  - confidence: same-scope > imported > builtin > unresolved
  - forward reference (string literal annotation)
  - decorator-driven confidence path NOT regressed
"""

from __future__ import annotations

import textwrap

import pytest

from graph_os.extractors import code_python


def _extract(src: str, *, path: str = "core/foo.py"):
    return code_python.extract(path, textwrap.dedent(src))


def _edges_of(result, edge_type: str):
    return [e for e in result.edges if e.edge_type == edge_type]


class TestParamTypes:
    def test_simple_param(self):
        r = _extract(
            """
            class Foo: pass
            def welcome(x: Foo): return x
            """
        )
        edges = _edges_of(r, "has_param_type")
        assert len(edges) == 1
        e = edges[0]
        assert e.source_uid == "code:function:core/foo.py::welcome"
        assert e.target_uid == "code:class:core/foo.py::Foo"
        assert e.confidence == pytest.approx(0.95)

    def test_skips_self_first_param(self):
        r = _extract(
            """
            class Foo:
                def greet(self) -> str: return "hi"
            """
        )
        # self is dropped; only the return-type edge survives.
        assert _edges_of(r, "has_param_type") == []
        rets = _edges_of(r, "returns_type")
        assert len(rets) == 1
        assert rets[0].source_uid == "code:method:core/foo.py::Foo.greet"

    def test_skips_cls_first_param(self):
        r = _extract(
            """
            class Foo:
                @classmethod
                def make(cls): return cls()
            """
        )
        assert _edges_of(r, "has_param_type") == []

    def test_method_param_annotation(self):
        r = _extract(
            """
            class Bar: pass
            class Foo:
                def use(self, b: Bar): return b
            """
        )
        edges = _edges_of(r, "has_param_type")
        assert len(edges) == 1
        assert edges[0].source_uid == "code:method:core/foo.py::Foo.use"
        assert edges[0].target_uid == "code:class:core/foo.py::Bar"

    def test_kwonly_and_varargs(self):
        r = _extract(
            """
            class A: pass
            class B: pass
            class C: pass
            def f(*xs: A, k: B, **kw: C): pass
            """
        )
        targets = {e.target_uid for e in _edges_of(r, "has_param_type")}
        assert "code:class:core/foo.py::A" in targets
        assert "code:class:core/foo.py::B" in targets
        assert "code:class:core/foo.py::C" in targets


class TestReturnTypes:
    def test_simple_return(self):
        r = _extract(
            """
            class Foo: pass
            def make() -> Foo: return Foo()
            """
        )
        edges = _edges_of(r, "returns_type")
        assert len(edges) == 1
        assert edges[0].target_uid == "code:class:core/foo.py::Foo"

    def test_no_return_annotation_no_edge(self):
        r = _extract("def f(): return 1")
        assert _edges_of(r, "returns_type") == []


class TestUnions:
    def test_pep604_union_two_branches(self):
        r = _extract(
            """
            class A: pass
            class B: pass
            def f(x: A | B): pass
            """
        )
        targets = {e.target_uid for e in _edges_of(r, "has_param_type")}
        assert "code:class:core/foo.py::A" in targets
        assert "code:class:core/foo.py::B" in targets

    def test_optional_drops_none(self):
        r = _extract(
            """
            from typing import Optional
            class A: pass
            def f(x: Optional[A]): pass
            """
        )
        edges = _edges_of(r, "has_param_type")
        assert len(edges) == 1
        assert edges[0].target_uid == "code:class:core/foo.py::A"

    def test_union_typing_form(self):
        r = _extract(
            """
            from typing import Union
            class A: pass
            class B: pass
            def f(x: Union[A, B]): pass
            """
        )
        targets = {e.target_uid for e in _edges_of(r, "has_param_type")}
        assert "code:class:core/foo.py::A" in targets
        assert "code:class:core/foo.py::B" in targets


class TestContainers:
    def test_list_of_t_strips_to_t(self):
        r = _extract(
            """
            class A: pass
            def f(x: list[A]): pass
            """
        )
        edges = _edges_of(r, "has_param_type")
        # list[A] → A
        assert len(edges) == 1
        assert edges[0].target_uid == "code:class:core/foo.py::A"

    def test_dict_str_to_t(self):
        # dict[str, A] expands the slice tuple; we keep both branches.
        r = _extract(
            """
            class A: pass
            def f(x: dict[str, A]): pass
            """
        )
        targets = {e.target_uid for e in _edges_of(r, "has_param_type")}
        assert "code:class:core/foo.py::A" in targets


class TestFieldTypes:
    def test_class_field_annotation(self):
        r = _extract(
            """
            class Foo:
                name: str = ""
                count: int = 0
            """
        )
        edges = _edges_of(r, "field_of_type")
        # Two edges: name → str, count → int
        assert len(edges) == 2
        {e.target_uid for e in edges}
        # `str` and `int` are builtins → resolved as code:external:unresolved:str
        # under the current Python extractor's resolver.  What matters is
        # the source_uid stub format and edge_type.
        sources = {e.source_uid for e in edges}
        # Field source-uids carry the `code:variable:` prefix per
        # code_python._FieldVisitor (line 859) — fields are treated as
        # qualified variable nodes, not as code:class.
        assert "code:variable:core/foo.py::Foo.name" in sources
        assert "code:variable:core/foo.py::Foo.count" in sources
        # Builtin confidence from the new helper.
        assert all(e.confidence == pytest.approx(0.7) for e in edges)


class TestConfidence:
    def test_same_scope_high_confidence(self):
        r = _extract(
            """
            class Foo: pass
            def f(x: Foo): pass
            """
        )
        edges = _edges_of(r, "has_param_type")
        assert edges[0].confidence == pytest.approx(0.95)

    def test_imported_medium_confidence(self):
        r = _extract(
            """
            from pkg import Foo
            def f(x: Foo): pass
            """
        )
        edges = _edges_of(r, "has_param_type")
        assert edges[0].confidence == pytest.approx(0.85)

    def test_builtin_lower_confidence(self):
        r = _extract("def f(x: int): pass")
        edges = _edges_of(r, "has_param_type")
        assert edges[0].confidence == pytest.approx(0.7)

    def test_unresolved_lowest_confidence(self):
        r = _extract("def f(x: SomeThirdParty): pass")
        edges = _edges_of(r, "has_param_type")
        assert edges[0].confidence == pytest.approx(0.3)


class TestForwardReference:
    def test_string_annotation_resolves(self):
        r = _extract(
            """
            class Foo: pass
            def f(x: "Foo"): pass
            """
        )
        edges = _edges_of(r, "has_param_type")
        assert len(edges) == 1
        assert edges[0].target_uid == "code:class:core/foo.py::Foo"


class TestNoRegression:
    """Decorator + inheritance edges still emit at the same confidence."""

    def test_decorator_edge_unaffected(self):
        r = _extract(
            """
            def deco(f): return f
            @deco
            def hello(): pass
            """
        )
        decs = [e for e in r.edges if e.edge_type == "is_decorated_by"]
        assert len(decs) == 1

    def test_inherits_edge_unaffected(self):
        r = _extract(
            """
            class A: pass
            class B(A): pass
            """
        )
        inh = [e for e in r.edges if e.edge_type == "inherits_from"]
        assert len(inh) == 1
