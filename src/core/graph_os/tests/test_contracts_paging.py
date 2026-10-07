"""cos_graph_contracts filters by the registering file's path and pages through every route."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_go")


def _service(name: str, count: int) -> str:
    routes = "".join(f'\tapp.Get("/{name}/r{index}", h)\n' for index in range(count))
    return (
        'package main\n\nimport "github.com/gofiber/fiber/v2"\n\n'
        "func h(c *fiber.Ctx) error { return nil }\n\n"
        f"func main() {{\n\tapp := fiber.New()\n{routes}}}\n"
    )


@pytest.fixture()
def contracts(tmp_path: Path, monkeypatch):
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools import graph as graph_tools
    from graph_os.tools.reindex_dispatch import dispatch

    files = {
        "go.mod": "module example.com/shop\n\ngo 1.22\n",
        "svc/a/main.go": _service("a", 6),
        "svc/b/main.go": _service("b", 5),
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

    def call(**kwargs) -> dict:
        return json.loads(graph_tools.cos_graph_contracts(kinds=("http",), **kwargs))["data"]

    return call


def _paths(data: dict) -> list[str]:
    return [item["path"] for item in data["http_routes"]]


def test_scope_keeps_only_the_routes_registered_under_it(contracts):
    data = contracts(scope="svc/b")

    assert sorted(_paths(data)) == [f"/b/r{index}" for index in range(5)]
    assert data["total_count"] == 5


def test_offset_pages_through_every_route(contracts):
    full = contracts()
    pages = []
    offset = 0
    while True:
        page = contracts(offset=offset, limit=4)
        pages += _paths(page)
        offset = page["meta"]["offset"] + page["count"]
        if not page["meta"]["result_truncated"]:
            break

    assert full["total_count"] == 11
    assert pages == _paths(full)
