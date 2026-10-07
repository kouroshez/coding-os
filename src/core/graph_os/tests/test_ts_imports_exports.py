"""TS imports bind by the exported name — default, renamed, values, barrels — and a dead one is reported."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_typescript")

FILES = {
    "ui/Card.tsx": (
        "export default function Card() {\n  return null;\n}\n"
        "export function useCard() {\n  return 1;\n}\n"
    ),
    "ui/theme.ts": (
        "import { memo } from 'react';\n"
        "export const theme = { color: 'red', spacing: 4 };\n"
        "export const Button = memo(function Button() { return null; });\n"
        "const helper = () => 1;\n"
        "const config = { debug: true };\n"
        "export { helper, config as default };\n"
    ),
    "ui/types.ts": "export interface Props { title: string }\n",
    "ui/index.ts": "export type { Props } from './types';\nexport { theme } from './theme';\n",
    "ui/Badge.astro": "---\nconst { label } = Astro.props;\n---\n<span>{label}</span>\n",
    "app/Screen.tsx": (
        "import Card, { useCard as useIt } from '../ui/Card';\n"
        "import settings, { theme, Button, helper } from '../ui/theme';\n"
        "import type { Props } from '../ui';\n"
        "import Badge from '../ui/Badge.astro';\n"
        "import { removedThing } from '../ui/types';\n"
        "export function Screen(props: Props) {\n"
        "  useIt();\n  helper();\n"
        "  return <Card><Button /><Badge /></Card>;\n"
        "}\n"
    ),
}


@pytest.fixture()
def graph(tmp_path: Path, monkeypatch):
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools import graph as graph_tools
    from graph_os.tools.reindex_dispatch import dispatch

    (tmp_path / ".coding-os").mkdir()
    for relative, text in FILES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    db = str(tmp_path / "graph.db")
    for relative in FILES:
        dispatch(tmp_path / relative, project_root=tmp_path, db_path=db, include_docs=False)
    test_backend = SqliteBackend(conn=init_db(db))
    test_backend.link_cross_file()
    monkeypatch.setattr(graph_tools, "_backend", lambda *, backend=None: test_backend)
    return db


def _bindings(db: str) -> dict[str, str]:
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT s.uid, t.uid FROM graph_edges_v12 e JOIN graph_nodes s ON s.id = e.source_id "
            "JOIN graph_nodes t ON t.id = e.target_id WHERE e.extractor = 'import_linker@v1'"
        ).fetchall()
    finally:
        conn.close()
    return {source.rpartition("::")[2]: target for source, target in rows}


def _calls_from(db: str, source: str) -> set[str]:
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT t.uid FROM graph_edges_v12 e JOIN graph_nodes s ON s.id = e.source_id "
            "JOIN graph_nodes t ON t.id = e.target_id "
            "WHERE s.uid = ? AND e.edge_type IN ('calls', 'constructs')",
            (source,),
        ).fetchall()
    finally:
        conn.close()
    return {row[0] for row in rows}


def test_default_renamed_value_and_barrel_imports_bind_by_the_exported_name(graph):
    bound = _bindings(graph)

    assert bound["Card"] == "code:function:ui/Card.tsx::Card"
    assert bound["useIt"] == "code:function:ui/Card.tsx::useCard"
    assert bound["settings"] == "code:variable:ui/theme.ts::config"
    assert bound["theme"] == "code:variable:ui/theme.ts::theme"
    assert bound["Button"] == "code:variable:ui/theme.ts::Button"
    assert bound["Props"] == "code:interface:ui/types.ts::Props"
    assert bound["Badge"] == "code:module:ui/Badge.astro"


def test_calls_and_components_follow_the_import_to_the_exported_symbol(graph):
    targets = _calls_from(graph, "code:function:app/Screen.tsx::Screen")

    assert {
        "code:function:ui/Card.tsx::useCard",
        "code:function:ui/theme.ts::helper",
        "code:function:ui/Card.tsx::Card",
        "code:variable:ui/theme.ts::Button",
    } <= targets


def test_an_import_of_a_name_its_module_does_not_define_is_reported(graph):
    from graph_os.tools import graph as graph_tools

    found = json.loads(graph_tools.cos_graph_undefined())["data"]["undefined"]

    assert [(item["name"], item["reason"], item["module"]) for item in found] == [
        ("removedThing", "not_exported", "ui/types.ts")
    ]


def test_commonjs_require_imports_and_binds_like_an_import(tmp_path: Path):
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools.reindex_dispatch import dispatch

    files = {
        "lib/price.ts": "export function roundPrice(value: number) {\n  return value;\n}\n",
        "app/metro.config.js": (
            "const { roundPrice: round } = require('../lib/price');\n"
            "const path = require('path');\n"
            "module.exports = () => round(path.sep.length);\n"
        ),
    }
    (tmp_path / ".coding-os").mkdir()
    for relative, text in files.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    db = str(tmp_path / "graph.db")
    for relative in files:
        dispatch(tmp_path / relative, project_root=tmp_path, db_path=db, include_docs=False)
    SqliteBackend(conn=init_db(db)).link_cross_file()

    conn = sqlite3.connect(db)
    try:
        edges = {
            (row[0], row[1])
            for row in conn.execute(
                "SELECT e.edge_type, t.uid FROM graph_edges_v12 e "
                "JOIN graph_nodes s ON s.id = e.source_id JOIN graph_nodes t ON t.id = e.target_id "
                "WHERE s.file_path = 'app/metro.config.js'"
            )
        }
    finally:
        conn.close()
    assert ("imports", "code:module:lib/price.ts") in edges
    assert ("imports", "code:module:npm:path") in edges
    assert ("imports", "code:function:lib/price.ts::roundPrice") in edges
    assert ("calls", "code:function:lib/price.ts::roundPrice") in edges
    assert not any("require" in target for _, target in edges)


def test_import_lines_skip_blank_lines_and_type_position_imports_are_type_only():
    from graph_os.extractors import code_ts

    source = (
        "// header\n\nimport { a } from './a';\n\n\nimport b from './b';\n"
        "type Mod = typeof import('./c');\ntype P = import('./d').Props;\n"
        "const lazy = () => import('./e').then((m) => m.default);\n"
    )
    result = code_ts.extract("x.ts", source)

    assert {(n.label, n.start_line) for n in result.nodes if n.kind.endswith("import")} == {
        ("import a", 3),
        ("import b", 6),
    }
    kinds = {
        e.target_uid.rpartition(":")[2]: e.edge_type
        for e in result.edges
        if e.edge_type in ("imports", "imports_type")
    }
    assert kinds == {
        "a.ts": "imports",
        "b.ts": "imports",
        "c.ts": "imports_type",
        "d.ts": "imports_type",
        "e.ts": "imports",
    }


def test_nested_handlers_are_scoped_and_jsx_belongs_to_its_component():
    from graph_os.extractors import code_ts

    source = (
        "export function Card() {\n"
        "  const onPress = () => track(Number('1'));\n"
        "  function track(v: number) { return v; }\n"
        "  return <View onPress={onPress} />;\n}\n"
        "export function List() {\n  const onPress = () => 2;\n  return <Card />;\n}\n"
    )
    result = code_ts.extract("ui/Card.tsx", source)
    functions = {n.uid.rpartition("::")[2] for n in result.nodes if n.kind == "code:function"}
    edges = {
        (e.source_uid.rpartition("::")[2], e.edge_type, e.target_uid.rpartition("::")[2])
        for e in result.edges
        if e.edge_type in ("calls", "constructs")
    }

    assert functions == {"Card", "Card.onPress", "Card.track", "List", "List.onPress"}
    assert ("Card.onPress", "calls", "Card.track") in edges
    assert ("List", "constructs", "Card") in edges
    assert not any(target.endswith("Number") and kind == "constructs" for _, kind, target in edges)
    assert code_ts.extract("bad.ts", "const x = {;\n").parse_errors


def test_default_references_include_renders_and_calls_through_variables(graph):
    from graph_os.tools import graph as graph_tools

    def sources(uid: str) -> set[str]:
        data = json.loads(graph_tools.cos_graph_references(uid))["data"]
        return {row["source_uid"] for row in data["references"]}

    screen = "code:function:app/Screen.tsx::Screen"
    assert screen in sources("code:function:ui/Card.tsx::Card")
    assert screen in sources("code:variable:ui/theme.ts::Button")


def test_a_files_references_count_the_files_that_reach_its_symbols_through_a_barrel(
    tmp_path: Path, monkeypatch
):
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools import graph as graph_tools
    from graph_os.tools.reindex_dispatch import dispatch

    files = {
        "ui/Button.tsx": (
            "export function Button() {\n  return <Label />;\n}\n"
            "function Label() {\n  return null;\n}\n"
        ),
        "ui/index.ts": "export * from './Button';\n",
        "app/A.tsx": "import { Button } from '../ui';\nexport const A = () => <Button />;\n",
        "app/B.tsx": "import { Button } from '../ui';\nexport const B = () => <Button />;\n",
    }
    (tmp_path / ".coding-os").mkdir()
    for relative, text in files.items():
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    db = str(tmp_path / "graph.db")
    for relative in files:
        dispatch(tmp_path / relative, project_root=tmp_path, db_path=db, include_docs=False)
    test_backend = SqliteBackend(conn=init_db(db))
    test_backend.link_cross_file()
    monkeypatch.setattr(graph_tools, "_backend", lambda *, backend=None: test_backend)

    data = json.loads(graph_tools.cos_graph_references("code:file:ui/Button.tsx"))["data"]
    files_seen = {row["source_uid"].split(":", 2)[2].split("::")[0] for row in data["references"]}

    assert files_seen == {"ui/index.ts", "app/A.tsx", "app/B.tsx"}
    assert data["source_files"] == 3


def test_class_expressions_and_mixins_keep_their_methods():
    from graph_os.extractors import code_ts

    source = (
        "export const withAccountApi = <T extends Ctor>(Base: T) =>\n"
        "  class extends Base {\n"
        "    async register(token: string) { return this.send(token); }\n"
        "    send(token: string) { return token; }\n"
        "  };\n"
        "export const Store = class {\n  save() { return 1; }\n};\n"
    )
    result = code_ts.extract("src/api/account.ts", source)
    nodes = {node.uid: node.kind for node in result.nodes}
    calls = {
        (edge.source_uid, edge.target_uid) for edge in result.edges if edge.edge_type == "calls"
    }
    mixin = "code:method:src/api/account.ts::withAccountApi.class"

    assert nodes["code:class:src/api/account.ts::Store"] == "code:class"
    assert nodes["code:method:src/api/account.ts::Store.save"] == "code:method"
    assert "code:variable:src/api/account.ts::Store" not in nodes
    assert nodes[f"{mixin}.register"] == "code:method"
    assert nodes["code:function:src/api/account.ts::withAccountApi"] == "code:function"
    assert (f"{mixin}.register", f"{mixin}.send") in calls
