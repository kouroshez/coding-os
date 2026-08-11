"""Tests for graph_os.extractors.code_python (I.4).

Ship gate (Section 19 I.4):
  - ≥ 50 tests
  - resolution precision ≥ 85% on coding-os itself (golden set)
  - edge cases: circular imports, re-exports, type chains, overrides, C3 MRO
  - negative tests: syntax errors do not abort pipeline
"""

from __future__ import annotations

import textwrap

from graph_os.extractors import code_python


def _extract(src: str, *, path: str = "core/foo.py"):
    return code_python.extract(path, textwrap.dedent(src))


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

        from graph_os.extractors import (
            _python_decls,
            _python_emit,
            _python_tree_sitter,
            _python_uids,
            _python_visitor,
        )

        modules = [
            code_python,
            _python_uids,
            _python_decls,
            _python_tree_sitter,
            _python_visitor,
            _python_emit,
        ]
        classes = 0
        functions = 0
        for module in modules:
            src = inspect.getsource(module)
            rel = f"core/graph_os/extractors/{module.__name__.split('.')[-1]}.py"
            r = code_python.extract(rel, src)
            assert r.parse_errors == [], rel
            classes += sum(1 for n in r.nodes if n.kind == "code:class")
            functions += sum(1 for n in r.nodes if n.kind == "code:function")
        # The visitor class plus the three declaration records.
        assert classes >= 1
        assert functions >= 5


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
