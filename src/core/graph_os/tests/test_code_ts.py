"""Tests for graph_os.extractors.code_ts (I.6).

Ship gate (Section 19 I.6): ≥ 40 tests, TS + TSX fixtures, imports /
decls / calls / JSX / decorators.
"""

from __future__ import annotations

import textwrap

import pytest

from graph_os.extractors import code_ts


def _extract(src: str, *, path: str = "frontend/src/foo.ts"):
    return code_ts.extract(path, textwrap.dedent(src).lstrip("\n"))


# ---------------------------------------------------------------------------
# File + module
# ---------------------------------------------------------------------------


class TestFileModule:
    def test_file_and_module_emitted(self):
        r = _extract("export const x = 1")
        files = [n for n in r.nodes if n.kind == "code:file"]
        modules = [n for n in r.nodes if n.kind == "code:module"]
        assert len(files) == 1 and len(modules) == 1
        assert files[0].lang == "ts"

    def test_tsx_lang_marker(self):
        r = _extract("export const x = 1", path="frontend/src/foo.tsx")
        files = [n for n in r.nodes if n.kind == "code:file"]
        assert files[0].lang == "tsx"


# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------


class TestImports:
    def test_named_import_emits_edge(self):
        r = _extract("import { foo } from './utils';")
        edges = [e for e in r.edges if e.edge_type == "imports"]
        assert any(e.target_uid == "code:module:frontend/src/utils.ts" for e in edges)

    def test_default_import(self):
        r = _extract("import React from 'react';")
        edges = [e for e in r.edges if e.edge_type == "imports"]
        assert any(e.target_uid == "code:module:npm:react" for e in edges)

    def test_star_import(self):
        r = _extract("import * as ns from './helpers';")
        edges = [e for e in r.edges if e.edge_type == "imports"]
        assert any(e.target_uid == "code:module:frontend/src/helpers.ts" for e in edges)

    def test_mixed_default_and_named(self):
        r = _extract("import React, { useState } from 'react';")
        edges = [e for e in r.edges if e.edge_type == "imports"]
        assert edges

    def test_side_effect_import(self):
        r = _extract("import './polyfill';")
        edges = [e for e in r.edges if e.edge_type == "imports"]
        assert any(e.target_uid == "code:module:frontend/src/polyfill.ts" for e in edges)

    def test_type_only_import(self):
        r = _extract("import type { Props } from './types';")
        edges = [e for e in r.edges if e.edge_type == "imports"]
        assert edges

    def test_export_from_emits_re_exports(self):
        r = _extract("export { foo } from './bar';")
        edges = [e for e in r.edges if e.edge_type == "re_exports"]
        assert len(edges) == 1

    def test_commented_import_ignored(self):
        r = _extract("// import { evil } from 'bad';\nexport const x = 1")
        imports = [e for e in r.edges if e.edge_type == "imports"]
        assert imports == []


# ---------------------------------------------------------------------------
# Decls
# ---------------------------------------------------------------------------


class TestDecls:
    def test_class(self):
        r = _extract("export class Foo {}")
        classes = [n for n in r.nodes if n.kind == "code:class"]
        assert len(classes) == 1
        assert classes[0].label == "Foo"

    def test_class_extends(self):
        r = _extract("class Bar extends Foo {}")
        inherits = [e for e in r.edges if e.edge_type == "inherits_from"]
        assert len(inherits) == 1

    def test_class_implements(self):
        r = _extract("class A implements IFoo, IBar {}")
        impls = [e for e in r.edges if e.edge_type == "implements"]
        assert len(impls) == 2

    def test_interface(self):
        r = _extract("export interface Props { name: string }")
        ifaces = [n for n in r.nodes if n.kind == "code:interface"]
        assert len(ifaces) == 1

    def test_interface_extends(self):
        r = _extract("interface B extends A {}")
        extends = [e for e in r.edges if e.edge_type == "extends"]
        assert extends

    def test_function_decl(self):
        r = _extract("export function hello(n: number) { return n; }")
        fns = [n for n in r.nodes if n.kind == "code:function"]
        assert len(fns) == 1
        assert fns[0].label == "hello"

    def test_arrow_function(self):
        r = _extract("export const add = (a: number, b: number) => a + b;")
        fns = [n for n in r.nodes if n.kind == "code:function"]
        assert len(fns) == 1
        assert fns[0].metadata.get("arrow") is True

    def test_async_function(self):
        r = _extract("async function fetchUser() {}")
        fns = [n for n in r.nodes if n.kind == "code:function"]
        assert len(fns) == 1

    def test_class_decorator_edges(self):
        r = _extract(
            """
            import { Controller } from 'nest';
            @Controller('/api')
            class UsersController {}
            """
        )
        decs = [e for e in r.edges if e.edge_type == "is_decorated_by"]
        assert any("Controller" in e.target_uid for e in decs)

    def test_generics_in_signature(self):
        r = _extract("export function identity<T>(x: T) { return x; }")
        fns = [n for n in r.nodes if n.kind == "code:function"]
        assert fns[0].label == "identity"


# ---------------------------------------------------------------------------
# Calls
# ---------------------------------------------------------------------------


class TestCalls:
    def test_call_to_local_function(self):
        r = _extract(
            """
            function greet() {}
            greet()
            """
        )
        calls = [e for e in r.edges if e.edge_type == "calls"]
        assert any(e.target_uid.endswith("::greet") for e in calls)

    def test_call_to_imported_symbol(self):
        r = _extract(
            """
            import { useState } from 'react';
            useState(0)
            """
        )
        calls = [e for e in r.edges if e.edge_type == "calls"]
        assert any("npm:react" in e.target_uid or "useState" in e.target_uid for e in calls)

    def test_constructor_call(self):
        r = _extract(
            """
            class User {}
            const u = User()
            """
        )
        ctors = [e for e in r.edges if e.edge_type == "constructs"]
        assert ctors

    def test_keyword_not_treated_as_call(self):
        # `if (x) { ... }` should not produce a call to `if`.
        r = _extract("if (true) { }")
        calls = [e for e in r.edges if e.edge_type == "calls"]
        assert not any(e.target_uid.endswith("::if") for e in calls)

    def test_unresolved_call_gets_low_confidence(self):
        r = _extract("mystery()")
        calls = [e for e in r.edges if e.edge_type == "calls"]
        assert any(c.confidence == pytest.approx(0.3) for c in calls)

    def test_string_content_not_parsed_as_call(self):
        r = _extract("const s = 'doEvil(); drop();'")
        calls = [e for e in r.edges if e.edge_type == "calls"]
        assert not any("doEvil" in e.target_uid for e in calls)

    def test_dotted_call_via_imported_module(self):
        r = _extract(
            """
            import * as api from './api';
            api.fetchUser()
            """
        )
        calls = [e for e in r.edges if e.edge_type == "calls"]
        assert any("api" in e.target_uid or "fetchUser" in e.target_uid for e in calls)


# ---------------------------------------------------------------------------
# JSX
# ---------------------------------------------------------------------------


class TestJSX:
    def test_component_usage_in_tsx(self):
        r = _extract(
            """
            import { Button } from './Button';
            export const View = () => <Button label="Go" />
            """,
            path="frontend/src/View.tsx",
        )
        ctors = [e for e in r.edges if e.edge_type == "constructs"]
        assert any("Button" in e.target_uid for e in ctors)

    def test_lowercase_tag_not_a_component(self):
        r = _extract(
            "export const Card = () => <div>Hello</div>",
            path="frontend/src/Card.tsx",
        )
        ctors = [e for e in r.edges if e.edge_type == "constructs"]
        assert not any(e.target_uid.endswith("::div") for e in ctors)

    def test_ts_file_does_not_emit_jsx(self):
        r = _extract("const x = <Button />", path="frontend/src/Card.ts")
        ctors = [e for e in r.edges if e.edge_type == "constructs"]
        assert not any("Button" in e.target_uid for e in ctors)


# ---------------------------------------------------------------------------
# Invariants + determinism
# ---------------------------------------------------------------------------


class TestInvariants:
    _SRC = textwrap.dedent(
        """
        import { helper } from './util';
        export interface Opts { name: string }
        export class Service implements Opts {
          run() {
            helper();
          }
        }
        export const make = () => new Service();
        """
    )

    def test_deterministic(self):
        a = code_ts.extract("frontend/src/service.ts", self._SRC)
        b = code_ts.extract("frontend/src/service.ts", self._SRC)
        assert [n.uid for n in a.nodes] == [n.uid for n in b.nodes]
        assert [(e.source_uid, e.target_uid, e.edge_type) for e in a.edges] == [
            (e.source_uid, e.target_uid, e.edge_type) for e in b.edges
        ]

    def test_backend_round_trip(self, migrated_conn):
        from graph_os.backends.sqlite_backend import SqliteBackend

        backend = SqliteBackend(conn=migrated_conn)
        r = code_ts.extract("frontend/src/service.ts", self._SRC)
        n, e = backend.bulk_upsert(r.nodes, r.edges)
        assert n == len(r.nodes)
        assert e == len(r.edges)

    def test_empty_file(self):
        r = _extract("")
        assert any(n.kind == "code:file" for n in r.nodes)
        assert r.parse_errors == []

    def test_large_file_does_not_time_out(self):
        r = _extract("\n".join(f"export const fn{i} = () => {i};" for i in range(200)))
        fns = [n for n in r.nodes if n.kind == "code:function"]
        assert len(fns) >= 100

    def test_comments_do_not_produce_edges(self):
        r = _extract(
            """
            /* block comment with import { evil } from 'bad'; */
            // single-line import { also } from 'bad';
            import { good } from './good';
            """
        )
        imports = [e for e in r.edges if e.edge_type == "imports"]
        assert len(imports) == 1
        assert imports[0].target_uid.endswith("good.ts")

    def test_strings_do_not_produce_imports(self):
        r = _extract(
            """
            const sample = 'import { hidden } from \\"nope\\";';
            """
        )
        imports = [e for e in r.edges if e.edge_type == "imports"]
        assert imports == []


# ---------------------------------------------------------------------------
# Path alias smoke
# ---------------------------------------------------------------------------


class TestPathAliases:
    def test_bare_specifier_treated_as_npm(self):
        r = _extract("import x from '@/shared/foo';")
        imports = [e for e in r.edges if e.edge_type == "imports"]
        # We model unresolved path aliases as npm specifiers until the
        # tsconfig resolver arrives — documented approximation.
        assert any(e.target_uid.startswith("code:module:npm:") for e in imports)

    def test_relative_dotdot_resolves(self):
        r = _extract(
            "import { x } from '../other';",
            path="frontend/src/sub/foo.ts",
        )
        imports = [e for e in r.edges if e.edge_type == "imports"]
        assert any(e.target_uid == "code:module:frontend/src/other.ts" for e in imports)
