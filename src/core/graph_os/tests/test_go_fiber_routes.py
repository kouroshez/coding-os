"""Go Fiber routes come from typed routers: last argument handler, composed prefixes, no header reads."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from graph_os.extractors import code_go

pytest.importorskip("tree_sitter_go")

HANDLER = """package shop

import (
	"example.com/shop/internal/auth"
	f "github.com/gofiber/fiber/v2"
)

func (h *Handler) Register(app *f.App, limiter f.Handler) {
	api := app.Group("/api/v1/", limiter)
	api.Get("/items/", auth.RequireUser, h.list)
	api.Post("", h.create)
	app.Route("/admin", func(r f.Router) {
		r.Get("/stats", func(c *f.Ctx) error { return c.SendString(h.stats()) })
	})
	internal := f.New()
	internal.Get("/ping", ping)
	app.Mount("/internal", internal)
	h.registerReports(api)
}

func (h *Handler) registerReports(r f.Router) {
	r.Get("/reports", h.reports)
}

func registerOrphans(r f.Router) {
	r.Get("/orphans", ping)
}

func inspect(resp *http.Response, c *f.Ctx) {
	_ = resp.Header.Get("Content-Type")
	_ = c.Get("X-Request-Id")
}

func main() {
	server := NewServer()
	server.Get("/healthz", ping)
}
"""
METHODS = """package shop

import f "github.com/gofiber/fiber/v2"

type Handler struct{}

func (h *Handler) list(c *f.Ctx) error { return nil }

func ping(c *f.Ctx) error { return nil }
"""


def _routes() -> dict[str, dict]:
    result = code_go.extract("internal/shop/handler.go", HANDLER)
    return {n.uid: dict(n.metadata) for n in result.nodes if n.kind == "cos:route"}


def _calls(route_uid: str) -> set[str]:
    result = code_go.extract("internal/shop/handler.go", HANDLER)
    return {
        e.target_uid for e in result.edges if e.source_uid == route_uid and e.edge_type == "calls"
    }


def test_groups_routes_and_mounts_compose_their_prefixes_without_trailing_slashes():
    assert set(_routes()) >= {
        "cos:route:GET:/api/v1/items",
        "cos:route:POST:/api/v1",
        "cos:route:GET:/admin/stats",
        "cos:route:GET:/internal/ping",
    }


def test_the_last_argument_is_the_handler_and_the_rest_are_middleware():
    items = _routes()["cos:route:GET:/api/v1/items"]

    assert (items["handler"], items["middleware"]) == ("h.list", ["auth.RequireUser"])
    assert _calls("cos:route:GET:/api/v1/items") == {
        "code:external:gopkg:internal/shop:Handler.list",
        "code:external:example.com/shop/internal/auth:RequireUser",
    }


def test_an_inline_handler_is_the_function_that_registers_it():
    assert _calls("cos:route:GET:/admin/stats") == {
        "code:method:internal/shop/handler.go::Handler.Register"
    }


def test_a_router_passed_in_the_same_file_carries_its_callers_prefix():
    routes = _routes()

    assert "cos:route:GET:/api/v1/reports" in routes
    assert "prefix" not in routes["cos:route:GET:/api/v1/reports"]
    orphans = routes["cos:route:GET:/orphans@internal/shop/handler.go::registerOrphans"]
    assert orphans["prefix"] == "unresolved"
    assert (orphans["router_owner"], orphans["router_param"]) == (
        "code:function:internal/shop/handler.go::registerOrphans",
        0,
    )


def test_header_reads_are_not_routes_but_an_untyped_app_still_is():
    routes = _routes()

    assert not any("Content-Type" in uid or "X-Request-Id" in uid for uid in routes)
    assert routes["cos:route:GET:/healthz"]["prefix"] == "unresolved"


def test_a_handler_in_another_file_of_the_package_links_to_the_real_method(tmp_path: Path):
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools.reindex_dispatch import dispatch

    (tmp_path / ".coding-os").mkdir()
    files = {"internal/shop/handler.go": HANDLER, "internal/shop/methods.go": METHODS}
    for relative, text in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    db = str(tmp_path / "graph.db")
    for relative in files:
        dispatch(tmp_path / relative, project_root=tmp_path, db_path=db, include_docs=False)
    SqliteBackend(conn=init_db(db)).link_cross_file()

    conn = sqlite3.connect(db)
    try:
        targets = {
            row[0]
            for row in conn.execute(
                "SELECT t.uid FROM graph_edges_v12 e JOIN graph_nodes s ON s.id = e.source_id "
                "JOIN graph_nodes t ON t.id = e.target_id "
                "WHERE s.uid = 'cos:route:GET:/api/v1/items' AND e.edge_type = 'calls'"
            )
        }
        framework = conn.execute(
            "SELECT metadata_json FROM graph_nodes WHERE uid = 'cos:route:GET:/internal/ping'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert "code:method:internal/shop/methods.go::Handler.list" in targets
    assert json.loads(framework)["framework"] == "fiber"
