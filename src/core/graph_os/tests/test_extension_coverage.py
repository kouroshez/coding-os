"""Astro, MDX, .mts/.cts, .bash/.zsh and shebang scripts reach the graph; JS keeps its language."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from graph_os.extractors import code_ts, contracts
from graph_os.extractors._astro_split import mask_astro
from graph_os.ingest.base import walk_local

ASTRO = """---
import Card from '../components/Card.astro';
import { pageTitle } from '../lib/title';
export function getStaticPaths() {
  return [];
}
const title = pageTitle('Home');
---
<Card title={title}>
  <p>{title}</p>
</Card>
<script>
  import { track } from '../lib/track';
  track('view');
</script>
<script type="application/ld+json">{"@type": "WebPage"}</script>
<style>p { color: red; }</style>
"""


def test_astro_mask_keeps_code_and_lines_and_drops_the_template():
    masked = mask_astro(ASTRO)

    assert len(masked) == len(ASTRO)
    assert masked.count("\n") == ASTRO.count("\n")
    assert "import Card from '../components/Card.astro';" in masked
    assert "track('view');" in masked
    assert "<p>" not in masked
    assert "WebPage" not in masked
    assert "color" not in masked


def test_astro_component_yields_imports_symbols_and_its_own_language():
    result = code_ts.extract("src/pages/index.astro", ASTRO)
    nodes = {node.uid: node for node in result.nodes}
    imports = {edge.target_uid for edge in result.edges if edge.edge_type == "imports"}

    assert nodes["code:file:src/pages/index.astro"].lang == "astro"
    assert nodes["code:function:src/pages/index.astro::getStaticPaths"].start_line == 4
    assert "code:module:src/components/Card.astro" in imports
    assert "code:module:src/lib/track.ts" in imports


def test_jsx_in_a_js_file_parses_and_keeps_the_js_language():
    source = (
        "export function Screen() {\n  return <Card />;\n}\nfunction Card() {\n  return null;\n}\n"
    )
    result = code_ts.extract("app/Screen.js", source)
    contract = contracts.extract("app/Screen.js", source)

    file_langs = {node.lang for node in result.nodes + contract.nodes if node.kind == "code:file"}
    constructs = {edge.target_uid for edge in result.edges if edge.edge_type == "constructs"}
    assert file_langs <= {"js", None}
    assert "code:function:app/Screen.js::Card" in constructs


def test_walk_picks_up_the_new_extensions_and_shebang_scripts(tmp_path):
    for relative in ("a.mts", "b.cts", "c.astro", "d.mdx", "e.bash", "f.zsh"):
        (tmp_path / relative).write_text("x\n", encoding="utf-8")
    (tmp_path / "bin").mkdir()
    (tmp_path / "bin" / "deploy").write_text("#!/usr/bin/env bash\necho hi\n", encoding="utf-8")
    (tmp_path / "bin" / "README").write_text("not a script\n", encoding="utf-8")

    walked = {path.relative_to(tmp_path).as_posix() for path in walk_local(tmp_path).files}

    assert walked == {"a.mts", "b.cts", "c.astro", "d.mdx", "e.bash", "f.zsh", "bin/deploy"}


@pytest.mark.parametrize(
    ("relative", "text", "expected_uid"),
    [
        ("lib/a.mts", "export function a() {}\n", "code:function:lib/a.mts::a"),
        ("lib/b.cts", "export function b() {}\n", "code:function:lib/b.cts::b"),
        ("ops/run.bash", "run() { :; }\n", "code:function:ops/run.bash::run"),
        ("bin/deploy", "#!/bin/sh\nship() { :; }\n", "code:function:bin/deploy::ship"),
        ("docs/guide.mdx", "# Guide\n\nText.\n", "doc:file:docs/guide.mdx"),
    ],
)
def test_dispatch_routes_each_new_extension(tmp_path, relative, text, expected_uid):
    from graph_os.tools.reindex_dispatch import dispatch

    (tmp_path / ".coding-os").mkdir()
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    db = tmp_path / "graph.db"

    dispatch(path, project_root=tmp_path, db_path=str(db), include_docs=False)

    conn = sqlite3.connect(db)
    try:
        uids = {row[0] for row in conn.execute("SELECT uid FROM graph_nodes")}
    finally:
        conn.close()
    assert expected_uid in uids


def test_unknown_suffix_still_skipped(tmp_path):
    from graph_os.tools.reindex_dispatch import dispatch

    (tmp_path / ".coding-os").mkdir()
    path = Path(tmp_path / "notes.txt")
    path.write_text("plain\n", encoding="utf-8")

    report = dispatch(path, project_root=tmp_path, db_path=str(tmp_path / "graph.db"))

    assert report["layers"] == {} or "graph" not in report["layers"]
