"""An `.astro` template renders the components and calls the functions its frontmatter brings in."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_typescript")

FILES = {
    "src/components/Card.astro": "---\nconst { title } = Astro.props;\n---\n<h2>{title}</h2>\n",
    "src/components/icons.ts": "export const Star = () => null;\n",
    "src/lib/format.ts": "export function formatDate(value: Date) {\n  return value.toISOString();\n}\n",
    "src/pages/index.astro": (
        "---\n"
        "import Card from '../components/Card.astro';\n"
        "import * as Icons from '../components/icons';\n"
        "import { formatDate } from '../lib/format';\n"
        "const posts = [{ title: 'a', date: new Date() }];\n"
        "function label(text: string) { return text.toUpperCase(); }\n"
        "---\n"
        "<!-- <Ghost /> and {haunt()} are commented out -->\n"
        "<main>\n"
        "  {posts.map((post) => (\n"
        "    <Card title={label(post.title)} />\n"
        "  ))}\n"
        "  <Icons.Star />\n"
        "  <time>{formatDate(posts[0].date)}</time>\n"
        "</main>\n"
        "<script>\n  formatDate(new Date());\n</script>\n"
    ),
}


@pytest.fixture()
def edges(tmp_path: Path) -> set[tuple[str, str, str]]:
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools.reindex_dispatch import dispatch

    (tmp_path / ".coding-os").mkdir()
    (tmp_path / "package.json").write_text('{"name": "site"}', encoding="utf-8")
    for relative, text in FILES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    db = str(tmp_path / "graph.db")
    for relative in FILES:
        dispatch(tmp_path / relative, project_root=tmp_path, db_path=db, include_docs=False)
    SqliteBackend(conn=init_db(db)).link_cross_file()
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT s.file_path, e.edge_type, t.uid, e.source_span FROM graph_edges_v12 e "
            "JOIN graph_nodes s ON s.id = e.source_id JOIN graph_nodes t ON t.id = e.target_id "
            "WHERE s.file_path = 'src/pages/index.astro'"
        ).fetchall()
    finally:
        conn.close()
    return {(row[1], row[2], row[3]) for row in rows}


def test_template_tags_render_and_template_expressions_call(edges):
    page = "src/pages/index.astro"
    targets = {(kind, target) for kind, target, _ in edges}

    assert ("constructs", "code:module:src/components/Card.astro") in targets
    assert ("constructs", "code:function:src/components/icons.ts::Star") in targets
    assert ("calls", "code:function:src/pages/index.astro::label", f"{page}:11") in edges
    assert ("calls", "code:function:src/lib/format.ts::formatDate", f"{page}:14") in edges


def test_commented_tags_and_script_calls_are_not_template_edges():
    from graph_os.extractors import code_ts

    result = code_ts.extract("src/pages/index.astro", FILES["src/pages/index.astro"])
    template = {
        (edge.edge_type, edge.target_uid.rpartition(":")[2], edge.source_span)
        for edge in result.edges
        if edge.evidence and edge.evidence[0].signal_name.startswith("astro_")
    }

    page = "src/pages/index.astro"
    assert template == {
        ("constructs", "default", f"{page}:11"),
        ("calls", "label", f"{page}:11"),
        ("constructs", "Star", f"{page}:13"),
        ("calls", "formatDate", f"{page}:14"),
    }


def test_astro_virtual_modules_count_toward_astros_fan_in(tmp_path: Path, monkeypatch):
    import json

    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools import graph as graph_tools
    from graph_os.tools.reindex_dispatch import dispatch

    files = {
        "package.json": '{"name": "site", "dependencies": {"astro": "5.0.0"}}',
        "src/pages/blog.astro": "---\nimport { getCollection } from 'astro:content';\n---\n<p/>\n",
        "src/pages/hero.astro": "---\nimport { Image } from 'astro:assets';\n---\n<Image />\n",
        "astro.config.mjs": "import { defineConfig } from 'astro/config';\nexport default defineConfig({});\n",
        "src/env.ts": "import type { APIRoute } from 'astro';\nexport type Route = APIRoute;\n",
    }
    (tmp_path / ".coding-os").mkdir()
    for relative, text in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    db = str(tmp_path / "graph.db")
    for relative in files:
        dispatch(tmp_path / relative, project_root=tmp_path, db_path=db, include_docs=False)
    test_backend = SqliteBackend(conn=init_db(db))
    test_backend.link_cross_file()
    monkeypatch.setattr(graph_tools, "_backend", lambda *, backend=None: test_backend)

    data = json.loads(graph_tools.cos_graph_references("code:module:npm:astro"))["data"]

    assert data["source_files"] == 4


def test_a_call_in_a_template_comment_is_none_and_jsx_text_apostrophes_hide_no_call():
    from graph_os.extractors import code_ts

    page = "src/pages/note.astro"
    text = (
        "---\n"
        "function render() { return 1; }\n"
        "function label() { return 2; }\n"
        "---\n"
        "{/* render() rewrites this caption */}\n"
        "<p>{label()}</p>\n"
        "<p>It's {label()} — it's late</p>\n"
        "{[1].map((i) => <li>Don't miss {render()}, it's due</li>)}\n"
    )
    calls = {
        (edge.target_uid.rpartition("::")[2], edge.source_span)
        for edge in code_ts.extract(page, text).edges
        if edge.edge_type == "calls"
    }

    assert calls == {("label", f"{page}:6"), ("label", f"{page}:7"), ("render", f"{page}:8")}
