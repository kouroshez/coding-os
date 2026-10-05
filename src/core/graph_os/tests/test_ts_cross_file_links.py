"""TS/JS references reach the defining file once imports resolve as TypeScript does."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

HOME = "apps/console/src/pages/Home.tsx"
FILES = {
    "pnpm-workspace.yaml": "packages:\n  - 'packages/*'\n  - 'apps/*'\n",
    "apps/console/tsconfig.json": json.dumps(
        {"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["./src/*"]}}}
    ),
    "packages/kit/package.json": json.dumps(
        {"name": "@acme/kit", "exports": {".": "./src/index.ts"}}
    ),
    "packages/kit/src/index.ts": "export { formatDay } from './date';\nexport * from './Badge';\n",
    "packages/kit/src/date.ts": "export function formatDay(day: Date) {\n  return day;\n}\n",
    "packages/kit/src/Badge.tsx": "export function Badge() {\n  return <span />;\n}\n",
    "apps/console/src/lib/fetchers.ts": "export function loadItems() {\n  return [];\n}\n",
    "apps/console/src/Card.tsx": "export function Card() {\n  return <div />;\n}\n",
    HOME: (
        "import { loadItems } from '@/lib/fetchers';\n"
        "import { Card } from '../Card';\n"
        "import { formatDay, Badge } from '@acme/kit';\n"
        "export function Home() {\n"
        "  loadItems();\n"
        "  formatDay(new Date());\n"
        "  return <Card><Badge /></Card>;\n"
        "}\n"
    ),
}


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    (tmp_path / ".coding-os").mkdir()
    for relative, text in FILES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return tmp_path


def _dispatch_all(project: Path, db: str, *, home_last: bool) -> None:
    from graph_os.tools.reindex_dispatch import dispatch

    order = sorted(FILES, key=lambda relative: (relative == HOME) == home_last)
    for relative in order:
        dispatch(project / relative, project_root=project, db_path=db, include_docs=False)


def _edges_from_home(db: str) -> set[tuple[str, str]]:
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT e.edge_type, t.uid FROM graph_edges_v12 e "
            "JOIN graph_nodes s ON s.id = e.source_id "
            "JOIN graph_nodes t ON t.id = e.target_id WHERE s.file_path = ?",
            (HOME,),
        ).fetchall()
    finally:
        conn.close()
    return {(edge_type, uid) for edge_type, uid in rows}


def test_imports_land_on_the_real_module_nodes(project, tmp_path):
    db = str(tmp_path / "graph.db")
    _dispatch_all(project, db, home_last=True)

    edges = _edges_from_home(db)

    assert ("imports", "code:module:apps/console/src/lib/fetchers.ts") in edges
    assert ("imports", "code:module:apps/console/src/Card.tsx") in edges
    assert ("imports", "code:module:packages/kit/src/index.ts") in edges


def test_calls_and_jsx_reach_the_defining_symbol_through_aliases_and_barrels(project, tmp_path):
    db = str(tmp_path / "graph.db")
    _dispatch_all(project, db, home_last=True)

    edges = _edges_from_home(db)

    assert ("calls", "code:function:apps/console/src/lib/fetchers.ts::loadItems") in edges
    assert ("calls", "code:function:packages/kit/src/date.ts::formatDay") in edges
    assert ("constructs", "code:function:apps/console/src/Card.tsx::Card") in edges
    assert ("constructs", "code:function:packages/kit/src/Badge.tsx::Badge") in edges
    assert ("imports", "code:function:packages/kit/src/date.ts::formatDay") in edges


def test_global_link_binds_stubs_minted_before_their_target_was_indexed(project, tmp_path):
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend

    db = str(tmp_path / "graph.db")
    _dispatch_all(project, db, home_last=False)
    assert ("calls", "code:function:packages/kit/src/date.ts::formatDay") not in (
        _edges_from_home(db)
    )

    SqliteBackend(conn=init_db(db)).link_cross_file()

    assert ("calls", "code:function:packages/kit/src/date.ts::formatDay") in _edges_from_home(db)
