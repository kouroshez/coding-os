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
    module_targets = _calls_from(graph, "code:module:app/Screen.tsx")

    assert "code:function:ui/Card.tsx::useCard" in targets
    assert "code:function:ui/theme.ts::helper" in targets
    assert {
        "code:function:ui/Card.tsx::Card",
        "code:variable:ui/theme.ts::Button",
    } <= module_targets


def test_an_import_of_a_name_its_module_does_not_define_is_reported(graph):
    from graph_os.tools import graph as graph_tools

    found = json.loads(graph_tools.cos_graph_undefined())["data"]["undefined"]

    assert [(item["name"], item["reason"], item["module"]) for item in found] == [
        ("removedThing", "not_exported", "ui/types.ts")
    ]
