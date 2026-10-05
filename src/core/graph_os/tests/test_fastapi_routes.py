"""FastAPI routes read from the syntax tree and composed across the files that build their path."""

from __future__ import annotations

import json
import sqlite3
import textwrap
from pathlib import Path

from graph_os.extractors import contracts


def _routes(source: str, path: str = "app/api.py") -> dict[str, dict]:
    result = contracts.extract(path, textwrap.dedent(source))
    return {n.uid: dict(n.metadata) for n in result.nodes if n.kind == "cos:route"}


def test_every_route_form_is_read_and_docstring_examples_are_not():
    routes = _routes(
        '''
        """Usage: @app.get("/from-a-docstring")"""
        from fastapi import FastAPI

        app = FastAPI()

        @app.get("")
        def root(): ...

        @app.api_route("/items/{item_id:path}", methods=["GET", "PUT"])
        def item(item_id: str): ...

        @app.websocket("/ws")
        async def stream(socket): ...

        @app.post(path="/login")
        def login(): ...

        app.add_api_route("/health", health, methods=["HEAD"])
        '''
    )

    assert set(routes) == {
        "cos:route:GET:/",
        "cos:route:GET:/items/{item_id}",
        "cos:route:PUT:/items/{item_id}",
        "cos:route:ws:/ws",
        "cos:route:POST:/login",
        "cos:route:HEAD:/health",
    }


def test_a_router_that_may_be_mounted_elsewhere_keeps_a_file_scoped_uid():
    routes = _routes(
        """
        from fastapi import APIRouter

        router = APIRouter(prefix="/items")

        @router.get("/")
        def listing(): ...
        """
    )

    assert set(routes) == {"cos:route:GET:/items/@app/api.py"}
    assert routes["cos:route:GET:/items/@app/api.py"]["path"] == "/items/"


FILES = {
    "pyproject.toml": "[project]\nname = 'shop'\n",
    "shop/__init__.py": "",
    "shop/routers/__init__.py": "",
    "shop/routers/shared.py": (
        "from fastapi import APIRouter\n\nrouter = APIRouter(prefix='/items')\n"
    ),
    "shop/routers/items.py": (
        "from .shared import router\n\n\n@router.get('/{item_id}')\ndef read(item_id: int): ...\n"
    ),
    "shop/routers/orders.py": (
        "from fastapi import APIRouter\n\nrouter = APIRouter(prefix='/orders')\n\n\n"
        "@router.get('/{item_id}')\ndef read(item_id: int): ...\n"
    ),
    "shop/main.py": (
        "from fastapi import FastAPI\n\nfrom .routers import items, orders\n\n"
        "app = FastAPI()\napp.include_router(items.router, prefix='/api/v1')\n"
        "app.include_router(orders.router, prefix='/api/v1')\n"
    ),
}


def _build(root: Path) -> str:
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools.reindex_dispatch import dispatch

    (root / ".coding-os").mkdir(exist_ok=True)
    for relative, text in FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    db = str(root / "graph.db")
    for relative in FILES:
        dispatch(root / relative, project_root=root, db_path=db, include_docs=False)
    SqliteBackend(conn=init_db(db)).link_cross_file()
    return db


def _route_uids(db: str) -> set[str]:
    conn = sqlite3.connect(db)
    try:
        return {row[0] for row in conn.execute("SELECT uid FROM graph_nodes WHERE kind = 'route'")}
    finally:
        conn.close()


def test_prefixes_from_a_shared_router_and_the_including_app_compose(tmp_path: Path):
    db = _build(tmp_path)

    assert _route_uids(db) == {
        "cos:route:GET:/api/v1/items/{item_id}",
        "cos:route:GET:/api/v1/orders/{item_id}",
    }


def test_a_prefix_edited_in_the_app_moves_routes_declared_elsewhere(tmp_path: Path):
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools.reindex_dispatch import dispatch

    db = _build(tmp_path)
    main = tmp_path / "shop/main.py"
    main.write_text(main.read_text().replace("/api/v1", "/api/v2"), encoding="utf-8")
    dispatch(main, project_root=tmp_path, db_path=db, include_docs=False)
    SqliteBackend(conn=init_db(db)).link_cross_file()

    uids = _route_uids(db)
    assert "cos:route:GET:/api/v2/items/{item_id}" in uids
    metadata = json.loads(
        sqlite3.connect(db)
        .execute("SELECT metadata_json FROM graph_nodes WHERE uid LIKE '%/api/v2/orders%'")
        .fetchone()[0]
    )
    assert metadata["framework"] == "fastapi" and "prefix" not in metadata
