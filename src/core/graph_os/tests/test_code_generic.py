"""code_generic — table-driven polyglot baseline extractor (TASK-296).

Proves the single generic extractor yields stable-uid function/class nodes +
contains edges for any language whose grammar is installed (rust + ruby ship),
is idempotent, and fails open on a missing grammar / unsupported extension.
"""

from __future__ import annotations

import pytest

from graph_os.extractors import code_generic as g

pytest.importorskip("tree_sitter_rust")
pytest.importorskip("tree_sitter_ruby")


def _syms(result) -> dict[str, str]:
    return {n.uid: n.kind for n in result.nodes if n.kind in ("code:function", "code:class")}


def test_rust_functions_and_types():
    src = "struct Point { x: i32 }\nfn main() {}\nmod sub { pub fn helper() {} }\n"
    result = g.extract("src/lib.rs", src)
    syms = _syms(result)
    assert "code:class:src/lib.rs::Point" in syms
    assert "code:function:src/lib.rs::main" in syms
    assert "code:class:src/lib.rs::sub" in syms
    assert "code:function:src/lib.rs::helper" in syms
    # helper nests under the mod (file → mod → helper), not the file.
    assert any(
        e.source_uid == "code:class:src/lib.rs::sub"
        and e.target_uid == "code:function:src/lib.rs::helper"
        and e.edge_type == "contains"
        for e in result.edges
    )


def test_ruby_methods_and_classes():
    src = "class Foo\n  def bar; end\n  def self.baz; end\nend\ndef top; end\n"
    result = g.extract("app/foo.rb", src)
    syms = _syms(result)
    assert "code:class:app/foo.rb::Foo" in syms
    assert "code:function:app/foo.rb::bar" in syms
    assert "code:function:app/foo.rb::baz" in syms
    assert "code:function:app/foo.rb::top" in syms
    # bar nests under Foo.
    assert any(
        e.source_uid == "code:class:app/foo.rb::Foo"
        and e.target_uid == "code:function:app/foo.rb::bar"
        and e.edge_type == "contains"
        for e in result.edges
    )


def test_file_node_and_spine_always_present():
    result = g.extract("pkg/mod.rs", "fn a() {}\n")
    uids = {n.uid for n in result.nodes}
    assert "code:file:pkg/mod.rs" in uids
    assert "folder:." in uids  # repo-root spine anchor
    assert any(n.kind == "folder" and n.label == "pkg" for n in result.nodes)


def test_idempotent_same_content():
    src = "class A\n  def m; end\nend\n"
    a = _syms(g.extract("a.rb", src))
    b = _syms(g.extract("a.rb", src))
    assert a == b


def test_duplicate_sibling_names_disambiguated():
    # Two top-level methods of the same name → distinct stable uids.
    src = "def dup; end\ndef dup; end\n"
    result = g.extract("d.rb", src)
    fn_uids = [n.uid for n in result.nodes if n.kind == "code:function"]
    assert "code:function:d.rb::dup" in fn_uids
    assert "code:function:d.rb::dup#2" in fn_uids


def test_unsupported_extension_fails_open():
    """An extension with no _LANG_SPEC entry → file node only + a parse error,
    never a raise."""
    result = g.extract("x.zig", "fn a() void {}")
    assert {n.kind for n in result.nodes} <= {"code:file", "folder"}
    assert any(p.kind == "lang_unsupported" for p in result.parse_errors)


def test_lang_spec_node_types_exist_in_installed_grammars():
    """Grammar-drift guard (TASK-302): every node type _LANG_SPEC relies on
    must still appear when the installed grammar parses a sample exercising
    it. Fails if a tree-sitter upgrade renames a node type — which would
    otherwise make code_generic silently miss those symbols."""
    from graph_os import tree_sitter_overlay as ov

    samples = {
        "rust": "fn f(){}\nstruct S{}\nenum E{A}\ntrait T{ fn m(&self); }\nmod m{}\n",
        "ruby": "def m; end\nclass C\n  def self.x; end\nend\nmodule M; end\n",
    }
    for lang, src in samples.items():
        spec = g._LANG_SPEC[lang]
        parsed = ov.parse(lang, src)
        assert parsed is not None, f"grammar {lang} not installed"
        seen: set[str] = set()
        stack = [parsed.root]
        while stack:
            node = stack.pop()
            seen.add(node.type)
            stack.extend(node.children)
        expected = spec["func"] | spec["class"]
        missing = expected - seen
        assert not missing, f"{lang}: _LANG_SPEC node types absent from grammar (drift?): {missing}"


_POLYGLOT_CASES = [
    ("java", "tree_sitter_java", "A.java", "class C { void m(){} } interface I{}",
     {"code:class:A.java::C", "code:function:A.java::m", "code:class:A.java::I"}),
    ("c", "tree_sitter_c", "a.c", "struct S{int x;}; int main(){return 0;}",
     {"code:class:a.c::S", "code:function:a.c::main"}),
    ("cpp", "tree_sitter_cpp", "a.cpp", "class C{ void run(){} };",
     {"code:class:a.cpp::C", "code:function:a.cpp::run"}),
    ("c_sharp", "tree_sitter_c_sharp", "A.cs", "class C{ void M(){} } interface I{}",
     {"code:class:A.cs::C", "code:function:A.cs::M", "code:class:A.cs::I"}),
    ("scala", "tree_sitter_scala", "a.scala", "class C{ def m()={} }\nobject O{}\ntrait T{}",
     {"code:class:a.scala::C", "code:function:a.scala::m", "code:class:a.scala::O", "code:class:a.scala::T"}),
    ("kotlin", "tree_sitter_kotlin", "a.kt", "class C { fun m() {} }\nfun top() {}",
     {"code:class:a.kt::C", "code:function:a.kt::m", "code:function:a.kt::top"}),
    ("lua", "tree_sitter_lua", "a.lua", "function f() end\nlocal function gg() end",
     {"code:function:a.lua::f", "code:function:a.lua::gg"}),
]


@pytest.mark.parametrize("lang,grammar,fname,src,expected", _POLYGLOT_CASES)
def test_polyglot_language_extracts_symbols(lang, grammar, fname, src, expected):
    """Each broadened language (TASK-304) yields the expected function/class
    uids via the installed grammar — node types verified, names correct
    (incl. the C/C++ declarator-name fix)."""
    pytest.importorskip(grammar)
    result = g.extract(fname, src)
    assert expected <= set(_syms(result)), f"{lang}: missing {expected - set(_syms(result))}"


def test_missing_grammar_fails_open(monkeypatch):
    """A supported language whose grammar fails to load → file node only +
    dep_missing parse error (the overlay returns None)."""
    monkeypatch.setattr(g._ts_overlay, "parse", lambda *a, **k: None)
    result = g.extract("Main.java", "class Main { void run() {} }")
    assert not any(n.kind in ("code:function", "code:class") for n in result.nodes)
    assert any(p.kind == "dep_missing" for p in result.parse_errors)
