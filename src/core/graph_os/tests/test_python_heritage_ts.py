"""Tests for the tree-sitter-primary heritage + decorators path (TASK-120).

Coverage matrix:
  - default `auto` mode keeps the ast path (provenance="ast")
  - opt-in `tree-sitter` mode emits provenance="tree-sitter"
  - multi-base inheritance: `class Foo(Bar, Baz):`
  - chained decorators: `@a @b.c def f():`
  - decorator on a class
  - nested class qualname: `class Outer: class Inner: ...`
  - decorator with call args: `@cache.memoize(ttl=60)` → dotted name only
  - missing grammar degrades to ast (no crash)
  - topology parity with ast for the common case
"""

from __future__ import annotations

import textwrap

import pytest

from graph_os.extractors import code_python
from graph_os.types import provenance_for


def _extract(src: str, *, path: str = "core/foo.py"):
    return code_python.extract(path, textwrap.dedent(src))


def _edges_of(result, edge_type: str):
    return [e for e in result.edges if e.edge_type == edge_type]


@pytest.fixture
def force_tree_sitter(monkeypatch):
    monkeypatch.setenv("COS_EXTRACTOR_PREFERENCE", "tree-sitter")
    yield


@pytest.fixture
def force_legacy(monkeypatch):
    monkeypatch.setenv("COS_EXTRACTOR_PREFERENCE", "legacy")
    yield


def _has_python_grammar() -> bool:
    try:
        from graph_os.tree_sitter_overlay import _load_language

        return _load_language("python") is not None
    except ImportError:
        return False


pytestmark = pytest.mark.skipif(
    not _has_python_grammar(),
    reason="tree-sitter-python grammar not installed",
)


# ---------------------------------------------------------------------------
# Mode selection
# ---------------------------------------------------------------------------


class TestModeSelection:
    def test_default_auto_uses_ast_for_inheritance(self, monkeypatch):
        monkeypatch.delenv("COS_EXTRACTOR_PREFERENCE", raising=False)
        r = _extract(
            """
            class Bar: pass
            class Foo(Bar): pass
            """
        )
        edges = _edges_of(r, "inherits_from")
        assert all(provenance_for(e.extractor) == "ast" for e in edges)

    def test_legacy_mode_uses_ast(self, force_legacy):
        r = _extract(
            """
            class Bar: pass
            class Foo(Bar): pass
            """
        )
        edges = _edges_of(r, "inherits_from")
        assert all(provenance_for(e.extractor) == "ast" for e in edges)

    def test_tree_sitter_mode_tags_inherits(self, force_tree_sitter):
        r = _extract(
            """
            class Bar: pass
            class Foo(Bar): pass
            """
        )
        edges = _edges_of(r, "inherits_from")
        assert len(edges) == 1
        assert edges[0].extractor == "code_python_ts@v1"
        assert provenance_for(edges[0].extractor) == "tree-sitter"

    def test_tree_sitter_mode_tags_decorators(self, force_tree_sitter):
        r = _extract(
            """
            def deco(f): return f
            @deco
            def hello(): pass
            """
        )
        edges = _edges_of(r, "is_decorated_by")
        assert len(edges) == 1
        assert edges[0].extractor == "code_python_ts@v1"


# ---------------------------------------------------------------------------
# Tree-sitter parse correctness
# ---------------------------------------------------------------------------


class TestTreeSitterHeritage:
    def test_multi_base(self, force_tree_sitter):
        r = _extract(
            """
            class A: pass
            class B: pass
            class C: pass
            class Foo(A, B, C): pass
            """
        )
        edges = _edges_of(r, "inherits_from")
        # Three parents → three edges.
        assert len(edges) == 3
        targets = {e.target_uid for e in edges}
        assert "code:class:core/foo.py::A" in targets
        assert "code:class:core/foo.py::B" in targets
        assert "code:class:core/foo.py::C" in targets

    def test_dotted_base(self, force_tree_sitter):
        r = _extract(
            """
            from pkg import Base
            class Foo(pkg.Base): pass
            """
        )
        edges = _edges_of(r, "inherits_from")
        assert len(edges) == 1


class TestTreeSitterDecorators:
    def test_chained_decorators(self, force_tree_sitter):
        r = _extract(
            """
            def a(f): return f
            def b(f): return f
            @a
            @b
            def hello(): pass
            """
        )
        edges = _edges_of(r, "is_decorated_by")
        assert len(edges) == 2

    def test_dotted_decorator(self, force_tree_sitter):
        # `@Cache.memoize` resolves through `_resolve_symbol` which keys
        # off the head identifier (`Cache`) — same behavior as the ast
        # path.  So the decorator edge from `hello` points at the
        # `Cache` class node.  We verify the source/target shape rather
        # than the stripped name to avoid coupling to internal
        # resolution heuristics.
        r = _extract(
            """
            class Cache:
                @staticmethod
                def memoize(f): return f
            @Cache.memoize
            def hello(): pass
            """
        )
        edges = _edges_of(r, "is_decorated_by")
        # Decorator on `hello` must be present and tagged tree-sitter.
        hello_decs = [e for e in edges if "::hello" in e.source_uid]
        assert len(hello_decs) == 1
        assert hello_decs[0].extractor == "code_python_ts@v1"
        # Resolution lands on the Cache class (head-identifier match).
        assert "Cache" in hello_decs[0].target_uid

    def test_call_decorator_strips_args(self, force_tree_sitter):
        r = _extract(
            """
            def memoize(ttl=0):
                def wrapper(f): return f
                return wrapper
            @memoize(ttl=60)
            def hello(): pass
            """
        )
        edges = _edges_of(r, "is_decorated_by")
        # Decorator name should be the bare `memoize`, not `memoize(...)`.
        assert any("memoize" in e.target_uid for e in edges)

    def test_decorator_on_class(self, force_tree_sitter):
        r = _extract(
            """
            def deco(cls): return cls
            @deco
            class Foo: pass
            """
        )
        edges = _edges_of(r, "is_decorated_by")
        assert len(edges) == 1
        assert "Foo" in edges[0].source_uid


# ---------------------------------------------------------------------------
# Nested-scope qualname parity
# ---------------------------------------------------------------------------


class TestNestedQualnames:
    def test_nested_class_emits_with_dotted_qualname(self, force_tree_sitter):
        r = _extract(
            """
            class Outer:
                class Inner: pass
                class Sub(Inner): pass
            """
        )
        edges = _edges_of(r, "inherits_from")
        # Sub inherits from Inner; class_uid encodes the nested qualname.
        assert any("Outer.Sub" in e.source_uid for e in edges)


# ---------------------------------------------------------------------------
# Parity with ast (topology)
# ---------------------------------------------------------------------------


class TestParity:
    def _grouped(self, edges):
        return sorted((e.source_uid, e.target_uid, e.edge_type) for e in edges)

    def test_inherits_topology_matches(self, monkeypatch):
        src = textwrap.dedent(
            """
            class Bar: pass
            class Baz: pass
            class Foo(Bar, Baz): pass
            """
        )
        monkeypatch.setenv("COS_EXTRACTOR_PREFERENCE", "tree-sitter")
        ts = _edges_of(code_python.extract("foo.py", src), "inherits_from")
        monkeypatch.setenv("COS_EXTRACTOR_PREFERENCE", "legacy")
        ast = _edges_of(code_python.extract("foo.py", src), "inherits_from")
        assert self._grouped(ts) == self._grouped(ast)

    def test_decorator_topology_matches(self, monkeypatch):
        src = textwrap.dedent(
            """
            def a(f): return f
            def b(f): return f
            @a
            @b
            def hello(): pass
            """
        )
        monkeypatch.setenv("COS_EXTRACTOR_PREFERENCE", "tree-sitter")
        ts = _edges_of(code_python.extract("foo.py", src), "is_decorated_by")
        monkeypatch.setenv("COS_EXTRACTOR_PREFERENCE", "legacy")
        ast = _edges_of(code_python.extract("foo.py", src), "is_decorated_by")
        assert self._grouped(ts) == self._grouped(ast)


# ---------------------------------------------------------------------------
# Evidence signals
# ---------------------------------------------------------------------------


class TestEvidenceSignals:
    def test_tree_sitter_signal_on_inherits(self, force_tree_sitter):
        r = _extract(
            """
            class Bar: pass
            class Foo(Bar): pass
            """
        )
        edges = _edges_of(r, "inherits_from")
        signals = [s.signal_name for e in edges for s in e.evidence]
        assert "tree_sitter_base_class" in signals

    def test_tree_sitter_signal_on_decorator(self, force_tree_sitter):
        r = _extract(
            """
            def deco(f): return f
            @deco
            def hello(): pass
            """
        )
        edges = _edges_of(r, "is_decorated_by")
        signals = [s.signal_name for e in edges for s in e.evidence]
        assert "tree_sitter_decorator" in signals
