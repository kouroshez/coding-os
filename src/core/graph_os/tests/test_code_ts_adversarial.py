"""Adversarial correctness regression tests for code_ts.

Locks the abstract-class fix (abstract classes were invisible — the
tree-sitter node is `abstract_class_declaration`, the walker only handled
`class_declaration`) plus other tricky-but-correct heritage syntaxes.
"""

from __future__ import annotations

from graph_os.extractors import code_ts as t


def _classes(src, path="f.ts"):
    return [n.label for n in t.extract(path, src).nodes if n.kind == "code:class"]


def _edges(src, et, path="f.ts"):
    return [
        (e.source_uid.split("::")[-1], e.target_uid.split("::")[-1])
        for e in t.extract(path, src).edges
        if e.edge_type == et
    ]


def _type_targets(src, et, path="f.ts"):
    return [e.target_uid for e in t.extract(path, src).edges if e.edge_type == et]


def _nodes(src, path="f.ts"):
    return t.extract(path, src).nodes


class TestTypeResolution:
    def test_param_type_resolves_to_local_interface_forward_ref(self):
        # Foo declared AFTER f — deferred resolution must still bind it.
        src = "function f(x: Foo) {}\ninterface Foo {}"
        assert "code:interface:f.ts::Foo" in _type_targets(src, "has_param_type")

    def test_return_type_resolves_to_local_class(self):
        src = "function g(): Bar { return new Bar() }\nclass Bar {}"
        assert "code:class:f.ts::Bar" in _type_targets(src, "returns_type")

    def test_param_type_resolves_to_imported_symbol(self):
        src = "import { Baz } from './m'\nfunction h(x: Baz) {}"
        assert "code:external:./m:Baz" in _type_targets(src, "has_param_type")

    def test_unresolved_type_falls_back_cleanly(self):
        src = "function k(x: Unknowny) {}"
        assert "code:external:unresolved:Unknowny" in _type_targets(src, "has_param_type")


class TestAwaits:
    def test_awaited_call_is_awaits_not_calls(self):
        src = "async function run() { await fetch('/x') }"
        awaits = _type_targets(src, "awaits")
        assert any("fetch" in tgt for tgt in awaits)
        # The same call must NOT also appear as a plain `calls` edge.
        assert not any("fetch" in tgt for tgt in _type_targets(src, "calls"))

    def test_non_awaited_call_stays_calls(self):
        src = "function run() { plain() }\nfunction plain() {}"
        assert ("run", "plain") in _edges(src, "calls")
        assert _type_targets(src, "awaits") == []


class TestEnumNamespace:
    def test_enum_emits_node(self):
        nodes = _nodes("enum Color { Red, Green }")
        assert any(
            n.label == "Color" and n.metadata.get("ts_kind") == "enum"
            for n in nodes
            if n.kind == "code:class"
        )

    def test_namespace_emits_node(self):
        nodes = _nodes("namespace NS { export const x = 1; }")
        assert any(
            n.label == "NS" and n.metadata.get("ts_kind") == "namespace"
            for n in nodes
            if n.kind == "code:class"
        )

    def test_enum_used_as_param_type_resolves(self):
        src = "function f(c: Color) {}\nenum Color { Red, Green }"
        assert "code:class:f.ts::Color" in _type_targets(src, "has_param_type")


def _component_labels(src, path="f.tsx"):
    return {
        n.label
        for n in t.extract(path, src).nodes
        if n.kind == "code:function" and n.metadata.get("component")
    }


class TestReactComponent:
    def test_function_component_marked(self):
        assert "Card" in _component_labels("function Card() { return <div>hi</div> }")

    def test_arrow_component_marked(self):
        assert "Btn" in _component_labels("const Btn = () => <button>x</button>")

    def test_lowercase_not_component(self):
        # lowercase name = not a component even if it returns JSX.
        assert "helper" not in _component_labels("function helper() { return <div/> }")

    def test_pascal_without_jsx_not_component(self):
        # PascalCase but no JSX = plain function (factory/class-like), not a component.
        assert "Factory" not in _component_labels("function Factory() { return 42 }")

    def test_no_component_flag_in_plain_ts(self):
        # JSX can't appear in .ts; component detection is gated on tsx.
        assert _component_labels("function Card() { return 1 }", path="f.ts") == set()


class TestAbstractClass:
    def test_abstract_class_extracted(self):
        assert _classes("abstract class W {}") == ["W"]

    def test_export_abstract_class(self):
        assert _classes("export abstract class W {}") == ["W"]

    def test_export_default_abstract_class(self):
        assert _classes("export default abstract class W {}") == ["W"]

    def test_abstract_heritage(self):
        src = "export abstract class Svc extends Base implements IA, IB {}"
        assert _classes(src) == ["Svc"]
        assert any(t_.endswith("Base") for _, t_ in _edges(src, "inherits_from"))
        impls = {t_ for _, t_ in _edges(src, "implements")}
        assert {"IA", "IB"} <= {i.split(":")[-1] for i in impls}

    def test_abstract_this_method_resolves(self):
        src = "abstract class S {\n run(): void { this.helper() }\n helper(): void {}\n}"
        assert ("S.run", "S.helper") in _edges(src, "calls")


class TestHeritageSyntax:
    def test_chained_generics_in_extends(self):
        # extends Map<string, Array<number>> → base is Map (generics stripped).
        e = _edges("export class M extends Map<string, Array<number>> {}", "inherits_from")
        assert any(t_.endswith("Map") for _, t_ in e)

    def test_multi_implements_with_generic(self):
        impls = {t_ for _, t_ in _edges("class A implements Foo<T>, Bar {}", "implements")}
        names = {i.split(":")[-1] for i in impls}
        assert "Foo" in names and "Bar" in names

    def test_multiline_class_signature(self):
        src = "export class Svc\n  extends Base\n  implements IA, IB {}"
        assert _classes(src) == ["Svc"]
        assert any(t_.endswith("Base") for _, t_ in _edges(src, "inherits_from"))
