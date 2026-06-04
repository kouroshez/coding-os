"""Tests for graph_os.extractors.code_ts — regex fallback + module resolver.

The tree-sitter path is covered by test_code_ts.py; this file forces the
regex fallback (grammar absent) to exercise _extract_classes /
_interfaces / _functions / _arrow_fns / _calls / _jsx_components, plus
the pure import-resolution helpers.
"""

from __future__ import annotations

import textwrap

import pytest

from graph_os.extractors import code_ts


@pytest.fixture
def regex_mode(monkeypatch):
    # Force grammar-absent fallback: overlay parse returns None.
    monkeypatch.setattr("graph_os.tree_sitter_overlay.parse", lambda *a, **k: None)


def _extract(src: str, *, path: str = "frontend/src/foo.ts"):
    return code_ts.extract(path, textwrap.dedent(src).lstrip("\n"))


# ---------------------------------------------------------------------------
# Regex fallback — declarations
# ---------------------------------------------------------------------------


class TestRegexFallbackDecls:
    def test_class_with_extends_and_implements(self, regex_mode):
        r = _extract("export class Bar extends Foo implements IThing {}")
        classes = [n for n in r.nodes if n.kind == "code:class"]
        assert any(n.label == "Bar" for n in classes)
        assert any(e.edge_type == "inherits_from" for e in r.edges)
        assert any(e.edge_type == "implements" for e in r.edges)

    def test_interface_extends(self, regex_mode):
        r = _extract("export interface B extends A { name: string }")
        ifaces = [n for n in r.nodes if n.kind == "code:interface"]
        assert any(n.label == "B" for n in ifaces)
        assert any(e.edge_type == "extends" for e in r.edges)

    def test_function_decl(self, regex_mode):
        r = _extract("export function greet(n: number) { return n; }")
        fns = [n for n in r.nodes if n.kind == "code:function"]
        assert any(n.label == "greet" for n in fns)

    def test_arrow_function(self, regex_mode):
        r = _extract("export const add = (a: number, b: number) => a + b;")
        fns = [n for n in r.nodes if n.kind == "code:function"]
        assert any(n.label == "add" for n in fns)

    def test_calls_emit_edges(self, regex_mode):
        r = _extract(
            """
            function helper() {}
            function run() { helper(); }
            """
        )
        assert any(e.edge_type == "calls" for e in r.edges)

    def test_jsx_component_in_tsx(self, regex_mode):
        r = _extract(
            """
            import { Button } from './Button';
            export const View = () => <Button label="Go" />;
            """,
            path="frontend/src/View.tsx",
        )
        ctors = [e for e in r.edges if e.edge_type == "constructs"]
        assert any("Button" in e.target_uid for e in ctors)

    def test_lowercase_jsx_tag_not_component(self, regex_mode):
        r = _extract(
            "export const Card = () => <div>hi</div>;",
            path="frontend/src/Card.tsx",
        )
        ctors = [e for e in r.edges if e.edge_type == "constructs"]
        assert not any(e.target_uid.endswith("::div") for e in ctors)

    def test_ts_file_skips_jsx(self, regex_mode):
        # .ts (not .tsx) must not run the JSX extractor.
        r = _extract("const x = doThing();", path="frontend/src/plain.ts")
        assert all(e.edge_type != "constructs" for e in r.edges)

    def test_file_and_module_always(self, regex_mode):
        r = _extract("const x = 1;")
        assert any(n.kind == "code:file" for n in r.nodes)
        assert any(n.kind == "code:module" for n in r.nodes)


# ---------------------------------------------------------------------------
# _resolve_module_uid + _parse_clause — pure helpers
# ---------------------------------------------------------------------------


class TestResolveModuleUid:
    def test_relative_adds_ts_extension(self):
        assert (
            code_ts._resolve_module_uid("frontend/src/foo.ts", "./util")
            == "code:module:frontend/src/util.ts"
        )

    def test_relative_parent_traversal(self):
        assert (
            code_ts._resolve_module_uid("frontend/src/foo.ts", "../other")
            == "code:module:frontend/other.ts"
        )

    def test_relative_with_explicit_extension_kept(self):
        assert (
            code_ts._resolve_module_uid("frontend/src/foo.ts", "./types.ts")
            == "code:module:frontend/src/types.ts"
        )

    def test_bare_specifier_is_npm(self):
        assert (
            code_ts._resolve_module_uid("frontend/src/foo.ts", "react") == "code:module:npm:react"
        )


class TestParseClause:
    def test_named_imports(self):
        assert code_ts._parse_clause("{ a, b }") == ["a", "b"]

    def test_named_with_alias_keeps_local(self):
        assert code_ts._parse_clause("{ foo as bar }") == ["bar"]

    def test_star_import(self):
        assert code_ts._parse_clause("* as ns") == ["ns"]

    def test_default_import(self):
        assert code_ts._parse_clause("React") == ["React"]

    def test_empty_braces(self):
        assert code_ts._parse_clause("{}") == []


class TestApplyTsPath:
    def test_wildcard_substitution(self):
        out = code_ts._apply_ts_path("@shared/*", ("packages/shared/src/*",), "@shared/util")
        assert out == "packages/shared/src/util"

    def test_no_match_returns_none(self):
        assert code_ts._apply_ts_path("@shared/*", ("x/*",), "@other/util") is None

    def test_exact_pattern_match(self):
        assert code_ts._apply_ts_path("@app", ("src/app",), "@app") == "src/app"
