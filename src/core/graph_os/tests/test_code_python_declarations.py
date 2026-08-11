"""Tests for graph_os.extractors.code_python (I.4).

Ship gate (Section 19 I.4):
  - ≥ 50 tests
  - resolution precision ≥ 85% on coding-os itself (golden set)
  - edge cases: circular imports, re-exports, type chains, overrides, C3 MRO
  - negative tests: syntax errors do not abort pipeline
"""

from __future__ import annotations

import textwrap

import pytest

from graph_os.extractors import code_python


def _extract(src: str, *, path: str = "core/foo.py"):
    return code_python.extract(path, textwrap.dedent(src))


class TestFileAndModule:
    def test_file_node_present(self):
        r = _extract("x = 1")
        files = [n for n in r.nodes if n.kind == "code:file"]
        assert len(files) == 1
        assert files[0].uid == "code:file:core/foo.py"
        assert files[0].lang == "py"

    def test_module_node_present(self):
        r = _extract("x = 1")
        mods = [n for n in r.nodes if n.kind == "code:module"]
        assert len(mods) == 1
        assert mods[0].uid.startswith("code:module:")

    def test_module_name_drops_core_prefix(self):
        r = _extract("x = 1", path="core/foo/bar.py")
        mods = [n for n in r.nodes if n.kind == "code:module"]
        assert mods[0].uid == "code:module:foo.bar"

    def test_init_strips_filename(self):
        r = _extract("x = 1", path="core/pkg/__init__.py")
        mods = [n for n in r.nodes if n.kind == "code:module"]
        assert mods[0].uid == "code:module:pkg"

    def test_content_hash_deterministic(self):
        first = _extract("x = 1")
        second = _extract("x = 1")
        assert first.nodes[0].content_hash == second.nodes[0].content_hash


class TestDecls:
    def test_top_level_function(self):
        r = _extract("def foo(x): return x")
        fns = [n for n in r.nodes if n.kind == "code:function"]
        assert len(fns) == 1
        assert fns[0].label == "foo"
        assert fns[0].signature.startswith("def foo(")

    def test_async_function_signature(self):
        r = _extract("async def aio(x): pass")
        fns = [n for n in r.nodes if n.kind == "code:function"]
        assert fns[0].signature.startswith("async def aio(")

    def test_class_and_method(self):
        r = _extract(
            """
            class User:
                def get_name(self):
                    return 'x'
            """
        )
        classes = [n for n in r.nodes if n.kind == "code:class"]
        methods = [n for n in r.nodes if n.kind == "code:method"]
        assert len(classes) == 1
        assert len(methods) == 1
        assert methods[0].label == "get_name"
        assert methods[0].metadata.get("is_method") is True

    def test_nested_function_qualname(self):
        r = _extract(
            """
            def outer():
                def inner():
                    pass
            """
        )
        fns = [n for n in r.nodes if n.kind == "code:function"]
        qualnames = {n.metadata["qualname"] for n in fns}
        assert "outer" in qualnames
        assert "outer.inner" in qualnames

    def test_class_containment_edge(self):
        r = _extract(
            """
            class User:
                def m(self): pass
            """
        )
        contains = [e for e in r.edges if e.edge_type == "contains"]
        # Class → method containment.
        assert any(
            e.source_uid.startswith("code:class:") and e.target_uid.startswith("code:method:")
            for e in contains
        )

    def test_docstring_becomes_doc_blob(self):
        r = _extract('def f():\n    """The doc."""\n    pass')
        fn = next(n for n in r.nodes if n.kind == "code:function")
        assert fn.doc_blob == "The doc."


class TestInheritance:
    def test_same_file_base_high_confidence(self):
        r = _extract(
            """
            class Base: pass
            class Sub(Base): pass
            """
        )
        inherits = [e for e in r.edges if e.edge_type == "inherits_from"]
        assert len(inherits) == 1
        assert inherits[0].confidence >= 0.9

    def test_imported_base_medium_confidence(self):
        r = _extract(
            """
            from other import Base
            class Sub(Base): pass
            """
        )
        inherits = [e for e in r.edges if e.edge_type == "inherits_from"]
        assert inherits[0].confidence >= 0.7 and inherits[0].confidence < 0.95

    def test_unknown_base_low_confidence(self):
        r = _extract("class Sub(ThirdParty): pass")
        inherits = [e for e in r.edges if e.edge_type == "inherits_from"]
        assert inherits[0].confidence == pytest.approx(0.5)

    def test_multiple_bases_emit_multiple_edges(self):
        r = _extract(
            """
            class A: pass
            class B: pass
            class C(A, B): pass
            """
        )
        inherits = [e for e in r.edges if e.edge_type == "inherits_from"]
        # C → A, C → B.
        assert len(inherits) == 2


class TestDecorators:
    def test_decorator_edge_emitted(self):
        r = _extract(
            """
            from fastapi import app
            @app.get('/x')
            def handler(): pass
            """
        )
        decs = [e for e in r.edges if e.edge_type == "is_decorated_by"]
        assert decs
        assert any("app" in e.target_uid for e in decs)

    def test_local_decorator_resolves_to_local_symbol(self):
        r = _extract(
            """
            def mydec(f): return f
            @mydec
            def g(): pass
            """
        )
        decs = [e for e in r.edges if e.edge_type == "is_decorated_by"]
        assert any(e.target_uid.startswith("code:function:") and e.confidence >= 0.85 for e in decs)


class TestImports:
    def test_plain_import(self):
        r = _extract("import os")
        imps = [e for e in r.edges if e.edge_type == "imports"]
        assert len(imps) == 1
        assert imps[0].target_uid == "code:module:os"

    def test_from_import(self):
        r = _extract("from collections import deque")
        imps = [e for e in r.edges if e.edge_type == "imports"]
        assert imps[0].target_uid == "code:module:collections"

    def test_relative_import(self):
        r = _extract("from .utils import foo")
        imps = [e for e in r.edges if e.edge_type == "imports"]
        assert imps[0].target_uid.startswith("code:module:")

    def test_wildcard_import_flagged(self):
        r = _extract("from pkg import *")
        # Node must reflect wildcard.
        imp_nodes = [n for n in r.nodes if n.kind == "code:import"]
        assert any(n.metadata.get("wildcard") for n in imp_nodes)

    def test_aliased_import_uses_alias(self):
        r = _extract("import numpy as np\ndef f(): np.array([1])")
        # Call to np.array resolves via explicit_import.
        calls = [e for e in r.edges if e.edge_type == "calls"]
        assert calls
        assert any("numpy" in e.target_uid for e in calls)
