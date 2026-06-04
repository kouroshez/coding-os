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


def _calls(src, path="m.go"):
    """Return (src_tail, target_tail) for every same-file resolved calls edge."""
    r = g.extract(path, src)
    return [
        (e.source_uid.split("::")[-1], e.target_uid.split("::")[-1])
        for e in r.edges
        if e.edge_type == "calls" and "::" in e.source_uid and "::" in e.target_uid
    ]


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


class TestCallGraph:
    def test_bare_same_file_function_call(self):
        # `func A(){ B() }` → A calls B (same_scope, conf 0.9). Python parity.
        src = "package m\nfunc A() { B() }\nfunc B() {}"
        assert ("A", "B") in _calls(src)

    def test_forward_reference_call(self):
        # Go allows calling a function defined later in the file.
        src = "package m\nfunc A() { later() }\nfunc later() {}"
        assert ("A", "later") in _calls(src)

    def test_receiver_method_call_resolves(self):
        # `s.helper()` inside a method on *Server → Server.run calls Server.helper.
        src = (
            "package m\n"
            "type Server struct{}\n"
            "func (s *Server) run() { s.helper() }\n"
            "func (s *Server) helper() {}\n"
        )
        assert ("Server.run", "Server.helper") in _calls(src)

    def test_no_edge_for_unknown_bare_call(self):
        # `make`/builtins and cross-file functions are NOT same-file → no edge.
        src = "package m\nfunc A() { x := make([]int, 0); _ = x; Missing() }"
        assert _calls(src) == []

    def test_receiver_var_must_match(self):
        # A selector on a non-receiver var must NOT resolve to a method.
        src = (
            "package m\n"
            "type Server struct{}\n"
            "func (s *Server) helper() {}\n"
            "func (s *Server) run() { other.helper() }\n"
        )
        assert ("Server.run", "Server.helper") not in _calls(src)


class TestEmbedding:
    def test_embedded_struct_field(self):
        info = _info("package m\ntype S struct {\n *Base\n Name string\n}")
        assert "S" in info["classes"]
        assert any(b.endswith("Base") for b in info["inherits"])

    def test_interface_embedding(self):
        info = _info("package m\ntype R interface {\n io.Reader\n Close() error\n}")
        assert "R" in info["classes"]
        assert any("Reader" in b for b in info["inherits"])
