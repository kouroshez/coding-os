"""go.mod requires are graph edges; an undeclared import and an unused require are reported."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_go")

FILES = {
    "go.work": "go 1.22\n\nuse (\n\t./api\n\t./lib\n)\n",
    "api/go.mod": (
        "module example.com/api\n\ngo 1.22\n\n"
        "require github.com/gofiber/fiber/v2 v2.52.0\n\n"
        "require (\n"
        "\tgithub.com/google/uuid v1.6.0\n"
        "\tgithub.com/valyala/bytebufferpool v1.0.0 // indirect\n"
        "\tgolang.org/x/tools v0.20.0\n"
        "\tgithub.com/stale/unused v1.0.0\n"
        ")\n\n"
        "tool golang.org/x/tools/cmd/stringer\n"
    ),
    "api/main.go": (
        "package main\n\n"
        "import (\n"
        '\t"fmt"\n\n'
        '\t"example.com/lib/money"\n'
        '\t"github.com/gofiber/fiber/v2/middleware/cors"\n'
        '\t"github.com/google/uuid"\n'
        '\t"github.com/redis/go-redis/v9"\n'
        ")\n\n"
        "func main() {\n"
        "\tfmt.Println(money.Round(1), uuid.NewString(), cors.New(), redis.Nil)\n"
        "}\n"
    ),
    "lib/go.mod": "module example.com/lib\n\ngo 1.22\n",
    "lib/money/money.go": "package money\n\nfunc Round(v int) int { return v }\n",
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


def test_each_require_is_an_edge_to_the_module_node(graph):
    conn = sqlite3.connect(graph)
    try:
        required = {
            row[0]
            for row in conn.execute(
                "SELECT t.uid FROM graph_edges_v12 e JOIN graph_nodes s ON s.id = e.source_id "
                "JOIN graph_nodes t ON t.id = e.target_id "
                "WHERE e.edge_type = 'requires' AND s.uid = 'code:file:api/go.mod'"
            )
        }
    finally:
        conn.close()

    assert required == {
        "code:external:github.com/gofiber/fiber/v2",
        "code:external:github.com/google/uuid",
        "code:external:github.com/valyala/bytebufferpool",
        "code:external:golang.org/x/tools",
        "code:external:github.com/stale/unused",
    }


def test_an_undeclared_import_and_an_unused_require_are_reported(graph):
    from graph_os.tools import graph as graph_tools

    found = json.loads(graph_tools.cos_graph_undefined())["data"]["undefined"]
    gaps = {
        (item["file"], item["name"], item["reason"], item["line"])
        for item in found
        if item["reason"] in ("undeclared_module", "unused_requirement")
    }

    assert gaps == {
        ("api/main.go", "github.com/redis/go-redis/v9", "undeclared_module", 9),
        ("api/go.mod", "github.com/stale/unused", "unused_requirement", 11),
    }


def _gaps(tmp_path: Path, files: dict[str, str], monkeypatch) -> set[tuple[str, str]]:
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools import graph as graph_tools
    from graph_os.tools.reindex_dispatch import dispatch

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
    found = json.loads(graph_tools.cos_graph_undefined())["data"]["undefined"]
    return {(item["name"], item["reason"]) for item in found if item["lang"] == "go"}


def test_files_the_go_tool_ignores_or_the_walk_skips_cause_no_false_gaps(tmp_path, monkeypatch):
    files = {
        "go.mod": "module example.com/tool\n\ngo 1.22\n\nrequire github.com/used/inbuild v1.0.0\n",
        "main.go": "package main\n\nfunc main() {}\n",
        "build/build.go": 'package build\n\nimport "github.com/used/inbuild"\n\nvar _ = inbuild.X\n',
        "lint/testdata/src/a/a.go": 'package a\n\nimport "github.com/not/required"\n\nvar _ = required.Y\n',
    }

    assert _gaps(tmp_path, files, monkeypatch) == set()
