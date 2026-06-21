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


# ---------------------------------------------------------------------------
# File + module nodes
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Function / class / method nodes
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Inheritance
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Calls (7-step lookup subset)
# ---------------------------------------------------------------------------


class TestCalls:
    def test_same_scope_call_high_confidence(self):
        r = _extract(
            """
            def bar(): pass
            def foo(): bar()
            """
        )
        calls = [e for e in r.edges if e.edge_type == "calls"]
        assert any(e.target_uid.endswith("::bar") and e.confidence >= 0.5 for e in calls)

    def test_imported_function_call(self):
        r = _extract(
            """
            from utils import helper
            def f(): helper()
            """
        )
        calls = [e for e in r.edges if e.edge_type == "calls"]
        assert any("utils" in e.target_uid for e in calls)

    def test_constructor_emits_constructs_edge(self):
        r = _extract(
            """
            class Foo: pass
            def make(): return Foo()
            """
        )
        ctors = [e for e in r.edges if e.edge_type == "constructs"]
        assert ctors
        assert ctors[0].target_uid.endswith("::Foo")

    def test_unresolved_call_low_confidence(self):
        r = _extract("def f(): mystery_function()")
        calls = [e for e in r.edges if e.edge_type == "calls"]
        assert calls
        assert calls[0].confidence == pytest.approx(0.3)

    def test_dotted_call_via_imported_module(self):
        r = _extract(
            """
            import json
            def f(): json.dumps({})
            """
        )
        calls = [e for e in r.edges if e.edge_type == "calls"]
        assert any("json" in e.target_uid for e in calls)

    def test_evidence_signals_tagged_on_edges(self):
        r = _extract(
            """
            def helper(): pass
            def top(): helper()
            """
        )
        call = next(e for e in r.edges if e.edge_type == "calls")
        signals = {s.signal_name for s in call.evidence}
        assert "same_scope" in signals


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_syntax_error_does_not_crash(self):
        r = code_python.extract("core/bad.py", "def f(:\n")
        assert r.nodes  # file node still present
        assert any(p.kind == "syntax_error" for p in r.parse_errors)

    def test_empty_file_parses_clean(self):
        r = _extract("")
        assert r.parse_errors == []
        assert any(n.kind == "code:file" for n in r.nodes)

    def test_unicode_identifiers_tolerated(self):
        r = _extract("def ünicode(): pass")
        assert any(n.kind == "code:function" and n.label == "ünicode" for n in r.nodes)


# ---------------------------------------------------------------------------
# Determinism + backend round-trip
# ---------------------------------------------------------------------------


class TestPipelineInvariants:
    _SRC = textwrap.dedent(
        """
        from collections import OrderedDict

        class Cache(OrderedDict):
            def get_default(self, key, default=None):
                return self.get(key, default)

        def make_cache():
            return Cache()
        """
    )

    def test_deterministic_nodes_edges(self):
        a = code_python.extract("core/cache.py", self._SRC)
        b = code_python.extract("core/cache.py", self._SRC)
        assert [n.uid for n in a.nodes] == [n.uid for n in b.nodes]
        assert [(e.source_uid, e.target_uid, e.edge_type) for e in a.edges] == [
            (e.source_uid, e.target_uid, e.edge_type) for e in b.edges
        ]

    def test_backend_round_trip(self, migrated_conn):
        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        result = code_python.extract("core/cache.py", self._SRC)
        n_written, e_written = backend.bulk_upsert(result.nodes, result.edges)
        assert n_written == len(result.nodes)
        assert e_written == len(result.edges)

    def test_dogfood_self_extract(self):
        """The extractor must handle its own source without errors."""
        import inspect

        src = inspect.getsource(code_python)
        r = code_python.extract("core/graph_os/extractors/code_python.py", src)
        assert r.parse_errors == []
        # Expect at least one class + several functions.
        assert sum(1 for n in r.nodes if n.kind == "code:class") >= 1
        assert sum(1 for n in r.nodes if n.kind == "code:function") >= 5


# ---------------------------------------------------------------------------
# Edge-case coverage (plan §7.2)
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_circular_import_tolerated(self):
        src_a = "from b import B\nclass A(B): pass"
        src_b = "from a import A\nclass B: pass"
        ra = code_python.extract("core/a.py", src_a)
        rb = code_python.extract("core/b.py", src_b)
        # Both files parse — no exceptions, no fatal parse errors.
        assert not any(p.kind == "fatal" for p in ra.parse_errors)
        assert not any(p.kind == "fatal" for p in rb.parse_errors)

    def test_name_shadowing(self):
        """Local `foo` inside a function should not mask the module-level
        `foo` call edge's source scope — we record the call at module
        scope here since we only scan top-level function bodies."""
        src = textwrap.dedent(
            """
            def outer():
                def foo():
                    pass
                foo()
            """
        )
        r = code_python.extract("core/shadow.py", src)
        calls = [e for e in r.edges if e.edge_type == "calls"]
        # Nested foo() is recorded against outer.
        assert any(e.source_uid.endswith("::outer") for e in calls)

    def test_re_export_survives_pipeline(self):
        """An __init__.py re-exporting should not crash the extractor."""
        src = "from .a import Thing  # noqa\nfrom .b import Other  # noqa"
        r = code_python.extract("core/pkg/__init__.py", src)
        assert not any(p.kind == "fatal" for p in r.parse_errors)
        # Two import edges expected.
        imps = [e for e in r.edges if e.edge_type == "imports"]
        assert len(imps) == 2

    def test_decorated_staticmethod_still_emits_defines(self):
        src = textwrap.dedent(
            """
            class S:
                @staticmethod
                def helper():
                    pass
            """
        )
        r = code_python.extract("core/s.py", src)
        methods = [n for n in r.nodes if n.kind == "code:method"]
        assert len(methods) == 1
        decs = [e for e in r.edges if e.edge_type == "is_decorated_by"]
        assert decs

    def test_call_in_module_body_captured_at_module_scope(self):
        """Module-level calls (e.g. ``_db_conn = init_db()`` at server.py:51)
        are captured against the module uid. Closes the gap documented at
        Section 7.3 — server boot patterns and CLI dispatcher inits were
        previously dropped, leaving ``cos_graph_references`` blind to
        prod call-sites."""
        r = _extract("print('hi')")
        calls = [e for e in r.edges if e.edge_type == "calls"]
        assert len(calls) == 1
        assert calls[0].source_uid.startswith("code:module:")

    def test_module_level_call_resolves_via_unqualified_import(self):
        """``from <bare> import X`` at module scope followed by ``X()`` at
        module scope produces a call edge whose target is the external
        stub ``code:external:<bare>:X``. ``link_external_stubs`` then
        rewrites the stub to the canonical function uid when a real
        symbol of that name lives in ``**/<bare>.py`` (covered by
        ``test_link_external_stubs.py``)."""
        src = textwrap.dedent(
            """
            from database import init_db
            _db_conn = init_db()
            """
        )
        r = code_python.extract("core/thinking_os/server.py", src)
        calls = [e for e in r.edges if e.edge_type == "calls"]
        assert len(calls) == 1
        assert calls[0].target_uid == "code:external:database:init_db", (
            f"expected stub-style target, got {calls[0].target_uid}"
        )

    def test_function_local_import_resolves_call_to_external_stub(self):
        """A function that does ``from <pkg> import X`` THEN ``X()``
        inside its own body must produce a resolved call edge, not a
        ``code:external:unresolved:`` orphan. This is the sync_all.py
        / graph_commands.py pattern: defer the import to avoid top-level
        cycles, then invoke. Without this, prod CLI commands stayed
        invisible to ``cos_graph_references``."""
        src = textwrap.dedent(
            """
            def _apply():
                from thinking_os.database import init_db
                return init_db()
            """
        )
        r = code_python.extract("core/cli/sync.py", src)
        calls = [e for e in r.edges if e.edge_type == "calls"]
        assert len(calls) == 1
        # Target should be the bare-import stub (post-link rewritten by
        # link_external_stubs into the canonical uid).
        assert calls[0].target_uid == "code:external:thinking_os.database:init_db", (
            f"expected resolved stub, got {calls[0].target_uid}"
        )
        # Caller scope is the function, not module.
        assert calls[0].source_uid.endswith("::_apply")

    def test_module_level_call_skips_for_decl_statements(self):
        """The module-level walk must NOT double-count calls already
        captured inside FunctionDef / ClassDef bodies — that would
        produce duplicate ``calls`` edges."""
        src = textwrap.dedent(
            """
            def outer():
                inner()

            def inner():
                pass
            """
        )
        r = code_python.extract("core/dup.py", src)
        calls = [e for e in r.edges if e.edge_type == "calls"]
        # Exactly one call: outer -> inner. No module-level duplicate.
        assert len(calls) == 1
        assert calls[0].source_uid.endswith("::outer")


def test_self_method_resolves_to_enclosing_class():
    # GE: self.helper() must bind to the SAME class's helper, not the last
    # same-named method in the file (bare-name collision).
    r = _extract(
        """
        class A:
            def run(self): self.helper()
            def helper(self): pass
        class B:
            def run(self): self.helper()
            def helper(self): pass
        """
    )
    calls = {
        (e.source_uid.split("::")[-1], e.target_uid) for e in r.edges if e.edge_type == "calls"
    }
    assert ("A.run", "code:method:core/foo.py::A.helper") in calls
    assert ("B.run", "code:method:core/foo.py::B.helper") in calls


class TestExpressionStubGate:
    # TASK-405: an unresolved-call stub must be identifier-shaped — complex
    # receivers used to mint expression-shaped "identifier" junk.
    def test_expression_receiver_emits_no_stub_edge(self):
        r = _extract(
            """
            def f(a, b):
                return (a or b / 'docs').resolve()
            """
        )
        bad = [e for e in r.edges if e.target_uid.startswith("code:external:unresolved:")]
        assert bad == []
        assert not any(" " in n.uid or "'" in n.uid for n in r.nodes if n.kind == "identifier")

    def test_dotted_unresolved_still_minted(self):
        r = _extract("def f(): mystery.helper()")
        stubs = [e for e in r.edges if e.target_uid == "code:external:unresolved:mystery.helper"]
        assert stubs
