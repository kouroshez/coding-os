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
