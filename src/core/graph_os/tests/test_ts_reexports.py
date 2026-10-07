"""Barrels: renamed and type-only re-exports, cycles through them, and React Native platform twins."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_typescript")

FILES = {
    "package.json": '{"name": "app"}',
    "ui/Button.tsx": "import { theme } from './index';\nexport function Button() { return theme; }\n",
    "ui/Card.tsx": "export default function Panel() { return null; }\n",
    "ui/theme.ts": "export const theme = 'dark';\n",
    "ui/types.ts": "export interface Props { id: string }\n",
    "ui/d.ts": "export function delta() { return 4; }\n",
    "ui/index.ts": (
        "export { Button as PrimaryButton } from './Button';\n"
        "export { default as Card } from './Card';\n"
        "export * from './theme';\n"
        "export type { Props } from './types';\n"
        "import { delta as d } from './d';\n"
        "export { d as deltaFn };\n"
    ),
    "app/A.tsx": (
        "import { PrimaryButton, Card, deltaFn } from '../ui';\n"
        "import * as UI from '../ui';\n"
        "import type legacy = require('../ui/types');\n"
        "import Map from './Map';\n"
        "export function A() {\n"
        "  deltaFn();\n"
        "  return <><PrimaryButton /><Card /><UI.PrimaryButton /><Map /></>;\n"
        "}\n"
    ),
    "app/Map.ios.tsx": "export default function Map() { return null; }\n",
    "loop/a.ts": "import { helper } from './b';\nexport type AType = { n: number };\nhelper();\n",
    "loop/b.ts": (
        "import type { AType } from './a';\nexport { AType };\n"
        "export function helper(): AType | null { return null; }\n"
    ),
    "app/Map.android.tsx": "export default function Map() { return null; }\n",
    "mix/a.ts": (
        "import { helper } from './b';\nexport type AType = { n: number };\n"
        "export function base() { return 1; }\nhelper();\n"
    ),
    "mix/b.ts": (
        "import type { AType } from './a';\nexport { base } from './a';\nexport { AType };\n"
        "export function helper(): AType | null { return null; }\n"
    ),
}


@pytest.fixture(scope="module")
def graph(tmp_path_factory: pytest.TempPathFactory):
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools.reindex_dispatch import dispatch

    root = tmp_path_factory.mktemp("barrels")
    (root / ".coding-os").mkdir()
    for relative, text in FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    db = str(root / "graph.db")
    for relative in FILES:
        dispatch(root / relative, project_root=root, db_path=db, include_docs=False)
    backend = SqliteBackend(conn=init_db(db))
    backend.link_cross_file()
    return backend


def _edges(backend, source: str) -> set[tuple[str, str]]:
    return {
        (str(kind), str(target))
        for kind, target in backend._conn.execute(
            "SELECT e.edge_type, t.uid FROM graph_edges_v12 e "
            "JOIN graph_nodes s ON s.id = e.source_id JOIN graph_nodes t ON t.id = e.target_id "
            "WHERE s.uid = ?",
            (source,),
        ).fetchall()
    }


def test_a_renamed_re_export_binds_to_the_original_symbol(graph):
    used = _edges(graph, "code:function:app/A.tsx::A")

    assert ("constructs", "code:function:ui/Button.tsx::Button") in used
    assert ("constructs", "code:function:ui/Card.tsx::Panel") in used
    assert ("calls", "code:function:ui/d.ts::delta") in used
    assert not any(target.startswith("code:external:") for _, target in used)


def test_a_type_only_re_export_or_require_is_no_runtime_import(graph):
    rows = graph._conn.execute(
        "SELECT t.uid, ev.signal_name FROM graph_edges_v12 e "
        "JOIN graph_nodes s ON s.id = e.source_id JOIN graph_nodes t ON t.id = e.target_id "
        "JOIN graph_evidence_v12 ev ON ev.edge_id = e.id "
        "WHERE s.uid = 'code:module:ui/index.ts' AND e.edge_type = 're_exports'"
    ).fetchall()
    signals = {str(target): str(signal) for target, signal in rows}

    assert signals["code:module:ui/types.ts"] == "ts_type_reexport"
    assert ("imports_type", "code:module:ui/types.ts") in _edges(graph, "code:module:app/A.tsx")
    assert ("imports", "code:module:ui/types.ts") not in _edges(graph, "code:module:app/A.tsx")


def test_a_cycle_through_a_barrel_is_found(graph, monkeypatch):
    from graph_os.tools import graph as graph_tools

    monkeypatch.setattr(graph_tools, "_backend", lambda *, backend=None: graph)
    envelope = graph_tools.cos_graph_cycles(scope="imports")
    data = (json.loads(envelope) if isinstance(envelope, str) else envelope)["data"]

    assert {"code:module:ui/Button.tsx", "code:module:ui/index.ts"} in [
        set(cycle["members"]) for cycle in data["cycles"]
    ]
    assert not any("ui/types.ts" in cycle["members"] for cycle in data["cycles"])
    assert not any("code:module:loop/a.ts" in cycle["members"] for cycle in data["cycles"])
    # A value re-export and a type-only one of the same module are one edge; the value wins.
    assert {"code:module:mix/a.ts", "code:module:mix/b.ts"} in [
        set(cycle["members"]) for cycle in data["cycles"]
    ]


def test_an_import_of_a_platform_component_reaches_every_twin(graph):
    imported = _edges(graph, "code:module:app/A.tsx")

    assert ("imports", "code:module:app/Map.ios.tsx") in imported
    assert ("imports", "code:module:app/Map.android.tsx") in imported


def test_platform_twins_list_the_other_variants(tmp_path: Path):
    from graph_os.resolve_ts import platform_twins

    for name in ("Pay.tsx", "Pay.web.tsx", "Pay.native.ts", "Other.tsx"):
        (tmp_path / name).write_text("", encoding="utf-8")

    assert sorted(platform_twins(tmp_path, "Pay.tsx")) == ["Pay.native.ts", "Pay.web.tsx"]
    assert platform_twins(tmp_path, "Other.tsx") == []
