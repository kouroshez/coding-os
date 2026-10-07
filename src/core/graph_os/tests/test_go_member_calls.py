"""A Go method call reaches its method through a typed parameter, local, struct field or call result."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_go")

FILES = {
    "go.mod": "module example.com/shop\n\ngo 1.22\n",
    "store/repo.go": (
        "package store\n\n"
        "type Repo struct{}\n\n"
        "func (r *Repo) Find(id int) error { return nil }\n\n"
        "func NewRepo() *Repo { return &Repo{} }\n\n"
        "type Finder interface {\n\tFind(id int) error\n}\n"
    ),
    "svc/service.go": (
        "package svc\n\n"
        'import "example.com/shop/store"\n\n'
        "type Service struct {\n\trepo   *store.Repo\n\tfinder store.Finder\n}\n\n"
        "func New() (*Service, error) { return &Service{}, nil }\n"
    ),
    "svc/handlers.go": (
        "package svc\n\n"
        'import "example.com/shop/store"\n\n'
        "func (s *Service) Load() {\n\ts.repo.Find(1)\n\ts.finder.Find(2)\n}\n\n"
        "func Param(r *store.Repo) {\n\tr.Find(3)\n}\n\n"
        "func Local() {\n\tvar r store.Repo\n\tr.Find(4)\n\tx := &store.Repo{}\n\tx.Find(5)\n}\n\n"
        "func Built() {\n\tr := store.NewRepo()\n\tr.Find(6)\n}\n\n"
        "func Chained() {\n\tstore.NewRepo().Find(7)\n}\n\n"
        "func Same() {\n\ts, _ := New()\n\ts.Load()\n}\n"
    ),
}

FIND = "code:method:store/repo.go::Repo.Find"


@pytest.fixture()
def calls(tmp_path: Path) -> set[tuple[str, str]]:
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
            "SELECT s.uid, t.uid FROM graph_edges_v12 e JOIN graph_nodes s ON s.id = e.source_id "
            "JOIN graph_nodes t ON t.id = e.target_id WHERE e.edge_type = 'calls'"
        ).fetchall()
    finally:
        conn.close()
    return {(row[0], row[1]) for row in rows}


@pytest.mark.parametrize(
    ("caller", "callee"),
    [
        ("code:method:svc/handlers.go::Service.Load", FIND),
        ("code:method:svc/handlers.go::Service.Load", "code:method:store/repo.go::Finder.Find"),
        ("code:function:svc/handlers.go::Param", FIND),
        ("code:function:svc/handlers.go::Local", FIND),
        ("code:function:svc/handlers.go::Built", FIND),
        ("code:function:svc/handlers.go::Chained", FIND),
        ("code:function:svc/handlers.go::Same", "code:method:svc/handlers.go::Service.Load"),
    ],
)
def test_a_method_call_reaches_the_method_its_receivers_type_declares(calls, caller, callee):
    assert (caller, callee) in calls
