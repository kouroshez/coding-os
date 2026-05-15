"""Tests for graph_os.extractors.code_go (Wave 1 A3)."""
from __future__ import annotations

from graph_os.extractors import code_go


_HELLO = """\
package main

import "fmt"

import (
    "os"
    "strings"
)

func main() {
    fmt.Println("hi")
    os.Exit(0)
}

func helper(x int) int {
    return x + 1
}
"""

_TYPED = """\
package server

import "net/http"

type Server struct {
    addr string
}

type Handler interface {
    ServeHTTP(w http.ResponseWriter, r *http.Request)
}

func NewServer(addr string) *Server {
    return &Server{addr: addr}
}

func (s *Server) Start() error {
    return nil
}

func (s *Server) Stop() error {
    return nil
}
"""


def _by_kind(result, kind: str):
    return [n for n in result.nodes if n.kind == kind]


def _edges(result, edge_type: str):
    return [e for e in result.edges if e.edge_type == edge_type]


def test_extract_emits_file_and_module_pair():
    r = code_go.extract("svc/main.go", _HELLO)
    files = _by_kind(r, "code:file")
    mods = _by_kind(r, "code:module")
    assert len(files) == 1 and len(mods) == 1
    assert files[0].uid == "code:file:svc/main.go"
    assert mods[0].label == "main"


def test_extract_emits_top_level_funcs():
    r = code_go.extract("svc/main.go", _HELLO)
    funcs = _by_kind(r, "code:function")
    names = sorted(n.label for n in funcs)
    assert names == ["helper", "main"]


def test_extract_emits_methods_with_receiver():
    r = code_go.extract("server/server.go", _TYPED)
    methods = _by_kind(r, "code:method")
    labels = sorted(m.label for m in methods)
    assert labels == ["Server.Start", "Server.Stop"]


def test_extract_emits_struct_and_interface_as_class():
    r = code_go.extract("server/server.go", _TYPED)
    classes = _by_kind(r, "code:class")
    labels = sorted(c.label for c in classes)
    assert labels == ["Handler", "Server"]
    kinds = {c.metadata.get("go_kind") for c in classes}
    assert kinds == {"struct", "interface"}


def test_extract_emits_imports_single_and_grouped():
    r = code_go.extract("svc/main.go", _HELLO)
    imports = _edges(r, "imports")
    targets = sorted(e.target_uid for e in imports)
    assert "code:external:fmt" in targets
    assert "code:external:os" in targets
    assert "code:external:strings" in targets


def test_extract_emits_calls_with_low_confidence():
    r = code_go.extract("svc/main.go", _HELLO)
    calls = _edges(r, "calls")
    assert calls, "expected at least one call edge"
    for e in calls:
        assert 0 < e.confidence <= 0.6, f"call confidence too high: {e.confidence}"


def test_contains_edges_link_module_to_funcs():
    r = code_go.extract("svc/main.go", _HELLO)
    contains = _edges(r, "contains")
    src_uids = {e.source_uid for e in contains}
    # module → function + file → module
    mod_uid = code_go.module_uid("svc/main.go")
    file_uid = code_go.file_uid("svc/main.go")
    assert mod_uid in src_uids
    assert file_uid in src_uids


def test_empty_file_still_emits_spine():
    r = code_go.extract("empty.go", "")
    files = _by_kind(r, "code:file")
    mods = _by_kind(r, "code:module")
    assert files and mods


def test_method_receiver_strips_pointer_and_generics():
    src = """\
package x
type T[U any] struct{}
func (r *T[int]) Foo() {}
"""
    r = code_go.extract("x/x.go", src)
    methods = _by_kind(r, "code:method")
    assert methods and methods[0].label == "T.Foo"


def test_extract_never_raises_on_garbage():
    # Mixed garbage with a real func declaration on its own line.
    src = "(((not go)))\nfunc Foo() {}"
    r = code_go.extract("garbage.go", src)
    funcs = _by_kind(r, "code:function")
    assert any(n.label == "Foo" for n in funcs)


def test_extract_skips_inline_func_keyword_in_string():
    # func keyword inside a non-anchored position must not produce a node.
    src = '(((not go))) func Foo() {}'
    r = code_go.extract("inline.go", src)
    funcs = _by_kind(r, "code:function")
    assert not any(n.label == "Foo" for n in funcs)
