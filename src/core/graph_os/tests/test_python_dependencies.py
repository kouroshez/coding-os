"""Calls in parameter defaults, decorator arguments and class bodies belong to the symbol they define."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

FILES = {
    "app/__init__.py": "",
    "app/deps.py": (
        "def get_db():\n    return 1\n\n\ndef verify():\n    return 2\n\n\n"
        "def make_id():\n    return 3\n"
    ),
    "app/api.py": (
        "from fastapi import APIRouter, Depends\n"
        "from pydantic import BaseModel, Field\n\n"
        "from .deps import get_db, make_id, verify\n\n"
        "router = APIRouter()\n\n\n"
        "class Item(BaseModel):\n"
        "    id: str = Field(default_factory=make_id)\n\n\n"
        "@router.get('/items', dependencies=[Depends(verify)])\n"
        "def list_items(db=Depends(get_db)):\n"
        "    return []\n"
    ),
}


@pytest.fixture()
def edges(tmp_path: Path) -> set[tuple[str, str, str]]:
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
        rows = conn.execute(
            "SELECT s.uid, e.edge_type, t.uid FROM graph_edges_v12 e "
            "JOIN graph_nodes s ON s.id = e.source_id JOIN graph_nodes t ON t.id = e.target_id"
        ).fetchall()
    finally:
        conn.close()
    return {tuple(row) for row in rows}


def test_fastapi_dependencies_reach_the_functions_they_name(edges):
    handler = "code:function:app/api.py::list_items"

    assert (handler, "dispatches", "code:function:app/deps.py::get_db") in edges
    assert (handler, "dispatches", "code:function:app/deps.py::verify") in edges


def test_a_class_body_calls_what_its_fields_build_with(edges):
    assert (
        "code:class:app/api.py::Item",
        "dispatches",
        "code:function:app/deps.py::make_id",
    ) in edges
