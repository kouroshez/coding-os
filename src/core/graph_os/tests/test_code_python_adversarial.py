"""Adversarial correctness regression tests for code_python.

Locks the non-obvious-but-correct behaviours found during the graph
correctness audit: multiple inheritance, stacked decorators, self-method
resolution, the awaits-vs-calls edge distinction, and unicode idents.
These are the syntaxes most likely to silently mis-extract (the Go
generic-receiver bug was exactly this class).
"""

from __future__ import annotations

from graph_os.extractors import code_python as p


def _edges(src, et):
    r = p.extract("m.py", src)
    return [
        (e.source_uid.split("::")[-1], e.target_uid.split("::")[-1])
        for e in r.edges
        if e.edge_type == et
    ]


class TestInheritance:
    def test_multiple_inheritance_each_base(self):
        e = _edges("class C(A, B): pass", "inherits_from")
        assert ("C", "code:external:unresolved:A") in e
        assert ("C", "code:external:unresolved:B") in e

    def test_metaclass_kwarg_not_a_base(self):
        # `metaclass=Meta` is a keyword, not a base class.
        e = _edges("class C(A, metaclass=Meta): pass", "inherits_from")
        assert not any(t.endswith("Meta") for _, t in e)


class TestDecorators:
    def test_stacked_decorators_both_captured(self):
        e = _edges("import a\n@a.deco\n@property\ndef f(): pass", "is_decorated_by")
        assert len(e) >= 2


class TestSelfMethod:
    def test_sync_self_call_resolves(self):
        e = _edges("class S:\n  def run(self): self.helper()\n  def helper(self): pass", "calls")
        assert ("S.run", "S.helper") in e


class TestAwaitSemantics:
    def test_awaited_call_is_awaits_not_calls(self):
        src = "class S:\n  async def run(self): await self.fetch()\n  async def fetch(self): pass"
        # By design: an awaited call is an `awaits` edge, NOT a `calls` edge.
        assert _edges(src, "calls") == []
        assert ("S.run", "S.fetch") in _edges(src, "awaits")

    def test_awaited_module_fn_resolves(self):
        e = _edges("async def run():\n  await helper()\nasync def helper(): pass", "awaits")
        assert ("run", "helper") in e

    def test_non_awaited_async_self_call_is_calls(self):
        # An async method invoked WITHOUT await is still a plain `calls` edge.
        src = "class S:\n  async def run(self): self.fetch()\n  def fetch(self): pass"
        assert ("S.run", "S.fetch") in _edges(src, "calls")


class TestUnicode:
    def test_unicode_identifier_function_and_call(self):
        r = p.extract("m.py", "def café(): pass\ncafé()")
        assert any(n.label == "café" for n in r.nodes if n.kind == "code:function")
        assert any(e.target_uid.endswith("::café") for e in r.edges if e.edge_type == "calls")
