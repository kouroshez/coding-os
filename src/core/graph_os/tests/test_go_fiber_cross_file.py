"""A Fiber router passed to a function in another file or package gives its routes the caller's prefix."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_go")

FILES = {
    "go.mod": "module example.com/shop\n\ngo 1.22\n",
    "internal/admin/handler.go": (
        'package admin\n\nimport "github.com/gofiber/fiber/v2"\n\n'
        "type Handler struct{}\n\n"
        "func (h *Handler) Register(app *fiber.App) {\n"
        '\tgroup := app.Group("/admin/v1")\n'
        "\th.registerInsights(group)\n"
        "}\n"
    ),
    "internal/admin/insights.go": (
        'package admin\n\nimport "github.com/gofiber/fiber/v2"\n\n'
        "func (h *Handler) registerInsights(group fiber.Router) {\n"
        '\tgroup.Get("/pets", h.pets)\n'
        '\treports := group.Group("/reports")\n'
        '\treports.Get("/daily", h.daily)\n'
        "}\n\n"
        "func (h *Handler) pets(c *fiber.Ctx) error { return nil }\n\n"
        "func (h *Handler) daily(c *fiber.Ctx) error { return nil }\n"
    ),
    "cmd/api/main.go": (
        "package main\n\n"
        'import (\n\t"example.com/shop/internal/users"\n\t"github.com/gofiber/fiber/v2"\n)\n\n'
        "func main() {\n"
        "\tapp := fiber.New()\n"
        '\tv2 := app.Group("/v2")\n'
        "\tusers.Mount(v2)\n"
        "}\n"
    ),
    "internal/users/routes.go": (
        'package users\n\nimport "github.com/gofiber/fiber/v2"\n\n'
        'func Mount(r fiber.Router) {\n\tr.Get("/users/list", show)\n}\n\n'
        "func show(c *fiber.Ctx) error { return nil }\n"
    ),
    "internal/orphan/routes.go": (
        'package orphan\n\nimport "github.com/gofiber/fiber/v2"\n\n'
        'func Wire(r fiber.Router) {\n\tr.Get("/lost", lost)\n}\n\n'
        "func lost(c *fiber.Ctx) error { return nil }\n"
    ),
}


@pytest.fixture()
def routes(tmp_path: Path) -> dict[str, dict]:
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools.reindex_dispatch import dispatch

    (tmp_path / ".coding-os").mkdir()
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
        nodes = conn.execute(
            "SELECT id, uid, metadata_json FROM graph_nodes WHERE kind = 'route'"
        ).fetchall()
        handlers = {
            (source, target)
            for source, target in conn.execute(
                "SELECT s.uid, t.uid FROM graph_edges_v12 e JOIN graph_nodes s ON s.id = e.source_id "
                "JOIN graph_nodes t ON t.id = e.target_id "
                "WHERE s.kind = 'route' AND e.edge_type = 'calls'"
            )
        }
    finally:
        conn.close()
    found = {uid: json.loads(metadata) for _, uid, metadata in nodes}
    found["__handlers__"] = handlers  # type: ignore[assignment]
    return found


def test_a_router_passed_to_another_file_of_the_package_takes_its_prefix(routes):
    assert "cos:route:GET:/admin/v1/pets" in routes
    assert "cos:route:GET:/admin/v1/reports/daily" in routes
    assert "prefix" not in routes["cos:route:GET:/admin/v1/pets"]
    assert (
        "cos:route:GET:/admin/v1/pets",
        "code:method:internal/admin/insights.go::Handler.pets",
    ) in routes["__handlers__"]


def test_a_router_passed_to_another_package_takes_its_prefix(routes):
    assert "cos:route:GET:/v2/users/list" in routes


def test_a_router_nobody_passes_in_stays_relative_and_apart(routes):
    lost = routes["cos:route:GET:/lost@internal/orphan/routes.go"]

    assert lost["prefix"] == "unresolved"
    assert not any(uid.startswith("cos:route:GET:/pets") for uid in routes)
