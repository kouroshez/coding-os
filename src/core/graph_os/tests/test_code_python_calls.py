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
    # an unresolved-call stub must be identifier-shaped — complex
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
