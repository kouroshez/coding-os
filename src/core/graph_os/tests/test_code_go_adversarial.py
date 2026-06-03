"""Adversarial correctness regression tests for code_go.

Locks the tricky-but-correct Go syntaxes: generics (func + receiver —
the latter was the _parse_receiver bug fixed in this audit), variadic +
multi-param signatures, embedded struct/interface → inherits edges.
"""

from __future__ import annotations

from graph_os.extractors import code_go as g


def _info(src, path="m.go"):
    r = g.extract(path, src)
    return {
        "funcs": [n.label for n in r.nodes if n.kind == "code:function"],
        "methods": [n.label for n in r.nodes if n.kind == "code:method"],
        "classes": [n.label for n in r.nodes if n.kind == "code:class"],
        "inherits": [
            e.target_uid.split("::")[-1]
            for e in r.edges
            if e.edge_type in ("inherits_from", "embeds", "extends")
        ],
    }


class TestSignatures:
    def test_generic_function(self):
        assert "Map" in _info("package m\nfunc Map[T any](x T) T { return x }")["funcs"]

    def test_variadic(self):
        assert "Printf" in _info("package m\nfunc Printf(f string, a ...any) {}")["funcs"]

    def test_multi_param_same_type(self):
        assert "add" in _info("package m\nfunc add(a, b int) int { return a + b }")["funcs"]

    def test_multi_return(self):
        assert "f" in _info("package m\nfunc f() (int, error) { return 0, nil }")["funcs"]


class TestGenericReceiver:
    def test_generic_method_receiver(self):
        # Regression for the _parse_receiver bug: `(c *Cont[T])` → method Cont.Get.
        info = _info("package m\nfunc (c *Cont[T]) Get() T { var z T; return z }")
        assert "Cont.Get" in info["methods"]
        assert "Cont" in info["classes"]


class TestEmbedding:
    def test_embedded_struct_field(self):
        info = _info("package m\ntype S struct {\n *Base\n Name string\n}")
        assert "S" in info["classes"]
        assert any(b.endswith("Base") for b in info["inherits"])

    def test_interface_embedding(self):
        info = _info("package m\ntype R interface {\n io.Reader\n Close() error\n}")
        assert "R" in info["classes"]
        assert any("Reader" in b for b in info["inherits"])
