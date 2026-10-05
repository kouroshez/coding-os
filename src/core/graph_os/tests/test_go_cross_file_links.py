"""Go calls, types and imports reach the defining file across a package and a module."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_go")

FILES = {
    "go.mod": "module example.com/app\n\ngo 1.22\n",
    "internal/svc/a.go": (
        "package svc\n\n"
        "func Run(items []int) {\n"
        "\thelper()\n"
        "\tlocalOnly()\n"
        "\tcount := len(items)\n"
        "\tcallback := func() {}\n"
        "\tcallback()\n"
        "\t_ = count\n"
        "}\n\n"
        "func localOnly() {}\n"
    ),
    "internal/svc/b.go": (
        "package svc\n\n"
        "func helper() {}\n\n"
        "type Store struct{}\n\n"
        "func (s *Store) Save() { s.flush() }\n"
    ),
    "internal/svc/c.go": "package svc\n\nfunc (s *Store) flush() {}\n",
    "api/routes.go": (
        "package api\n\n"
        'import st "example.com/app/internal/svc"\n\n'
        "func Register() { st.Run(nil) }\n"
    ),
    "api/handler.go": (
        'package api\n\nimport "example.com/app/internal/svc"\n\nfunc Handle(s *svc.Store) {}\n'
    ),
    "cmd/server/main.go": "package main\n\nfunc main() {}\n",
    "cmd/worker/main.go": "package main\n\nfunc main() {}\n",
}


@pytest.fixture()
def graph(tmp_path: Path) -> str:
    from graph_os.tools.reindex_dispatch import dispatch

    (tmp_path / ".coding-os").mkdir()
    for relative, text in FILES.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    db = str(tmp_path / "graph.db")
    for relative in FILES:
        if relative.endswith(".go"):
            dispatch(tmp_path / relative, project_root=tmp_path, db_path=db, include_docs=False)
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend

    SqliteBackend(conn=init_db(db)).link_cross_file()
    return db


def _edges(db: str) -> dict[tuple[str, str, str], float]:
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT s.uid, e.edge_type, t.uid, e.confidence FROM graph_edges_v12 e "
            "JOIN graph_nodes s ON s.id = e.source_id JOIN graph_nodes t ON t.id = e.target_id"
        ).fetchall()
    finally:
        conn.close()
    return {
        (source, edge_type, target): confidence for source, edge_type, target, confidence in rows
    }


def _uids(db: str) -> set[str]:
    conn = sqlite3.connect(db)
    try:
        return {row[0] for row in conn.execute("SELECT uid FROM graph_nodes")}
    finally:
        conn.close()


def test_same_package_call_in_another_file_binds_to_its_definition(graph):
    edges = _edges(graph)
    run = "code:function:internal/svc/a.go::Run"
    assert edges[(run, "calls", "code:function:internal/svc/b.go::helper")] == 0.9
    assert (run, "calls", "code:function:internal/svc/a.go::localOnly") in edges


def test_receiver_method_defined_in_a_sibling_file_binds(graph):
    edges = _edges(graph)
    save = "code:method:internal/svc/b.go::Store.Save"
    assert (save, "calls", "code:method:internal/svc/c.go::Store.flush") in edges


def test_aliased_import_call_and_qualified_type_reach_the_package(graph):
    edges = _edges(graph)
    assert (
        "code:function:api/routes.go::Register",
        "calls",
        "code:function:internal/svc/a.go::Run",
    ) in edges
    assert (
        "code:function:api/handler.go::Handle",
        "has_param_type",
        "code:class:internal/svc/b.go::Store",
    ) in edges
    assert ("code:module:api/routes.go", "imports", "code:package:go:internal/svc") in edges


def test_packages_are_keyed_by_directory_not_name(graph):
    uids = _uids(graph)
    assert {"code:package:go:cmd/server", "code:package:go:cmd/worker"} <= uids
    assert "code:package:go:main" not in uids
    assert "code:class:internal/svc/c.go::Store" not in uids  # no phantom receiver type


def test_builtins_and_local_bindings_mint_no_stub(graph):
    uids = _uids(graph)
    assert "code:external:gopkg:internal/svc:len" not in uids
    assert "code:external:gopkg:internal/svc:callback" not in uids


def test_type_parameters_are_neither_package_types_nor_calls():
    from graph_os.extractors import code_go

    source = (
        "package p\n\n"
        "func enumText[Value ~string](value *Value) *string { s := string(*value); return &s }\n\n"
        "func pick[Row any](rows []Row) Row { return Row(rows[0]) }\n\n"
        "type Box[Item any] struct{ v Item }\n\n"
        "func (b *Box[Item]) Put(v Item) { b.v = Item(v) }\n"
    )
    targets = {edge.target_uid for edge in code_go.extract("internal/p/p.go", source).edges}

    assert not any(
        target.endswith((":Value", ":Row", ":Item", "::Value", "::Row", "::Item"))
        for target in targets
    )
