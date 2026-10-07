"""Go interfaces list their methods, and a type that has them all implements the interface."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_go")

FILES = {
    "go.mod": "module example.com/shop\n\ngo 1.22\n",
    "domain/store.go": (
        'package domain\n\nimport "io"\n\n'
        "type User struct{ ID string }\n\n"
        "type Store interface {\n"
        "\tGet(id string) (*User, error)\n"
        "\tSave(u *User) error\n"
        "}\n\n"
        "type ReadStore interface {\n\tio.Reader\n\tGet(id string) (*User, error)\n}\n\n"
        "type Closer interface{ Close() }\n\n"
        "type Repo interface {\n\tStore\n\tCloser\n}\n\n"
        "type Number interface{ ~int | ~float64 }\n"
    ),
    "infra/sql.go": (
        'package infra\n\nimport "example.com/shop/domain"\n\n'
        "type SQLStore struct{ base }\n\n"
        "func (s *SQLStore) Get(id string) (*domain.User, error) { return nil, nil }\n"
    ),
    "infra/save.go": (
        'package infra\n\nimport "example.com/shop/domain"\n\n'
        "func (s *SQLStore) Save(u *domain.User) error { return nil }\n"
    ),
    "infra/base.go": "package infra\n\ntype base struct{}\n\nfunc (base) Close() {}\n",
    "infra/other.go": (
        'package infra\n\nimport "example.com/shop/domain"\n\n'
        "type Partial struct{}\n\n"
        "func (Partial) Get(id string) (*domain.User, error) { return nil, nil }\n\n"
        "type BadArity struct{}\n\n"
        "func (BadArity) Get(id string, n int) (*domain.User, error) { return nil, nil }\n\n"
        "func (BadArity) Save(u *domain.User) error { return nil }\n"
    ),
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


def _edges(db: str, edge_type: str) -> set[tuple[str, str]]:
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT s.uid, t.uid FROM graph_edges_v12 e JOIN graph_nodes s ON s.id = e.source_id "
            "JOIN graph_nodes t ON t.id = e.target_id WHERE e.edge_type = ?",
            (edge_type,),
        ).fetchall()
    finally:
        conn.close()
    return {(source.rpartition("::")[2], target.rpartition("::")[2]) for source, target in rows}


def test_an_interface_contains_a_node_for_each_method(graph):
    contained = _edges(graph, "contains")

    assert {
        ("Store", "Store.Get"),
        ("Store", "Store.Save"),
        ("Closer", "Closer.Close"),
    } <= contained


def test_a_type_with_every_method_implements_the_interface(graph):
    assert _edges(graph, "implements") == {
        ("SQLStore", "Store"),
        ("SQLStore", "Closer"),
        ("SQLStore", "Repo"),
        ("base", "Closer"),
    }


def test_references_to_an_interface_list_its_implementations(graph):
    from graph_os.tools import graph as graph_tools

    data = json.loads(graph_tools.cos_graph_references("code:class:domain/store.go::Store"))["data"]

    assert "code:class:infra/sql.go::SQLStore" in {row["source_uid"] for row in data["references"]}


def _reindex(graph: str, root: Path, relative: str) -> None:
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools.reindex_dispatch import dispatch

    dispatch(root / relative, project_root=root, db_path=graph, include_docs=False, force=True)
    SqliteBackend(conn=init_db(graph)).link_cross_file(file_path=relative)


def test_reindexing_the_types_own_file_keeps_methods_from_its_other_files(graph):
    root = Path(graph).parent
    _reindex(graph, root, "infra/sql.go")

    assert ("SQLStore", "Store") in _edges(graph, "implements")
    assert ("SQLStore", "SQLStore.Save") in _edges(graph, "contains")


def test_deleting_a_file_drops_the_implements_its_methods_made(graph):
    from graph_os.tools.reindex_dispatch import dispatch

    root = Path(graph).parent
    (root / "infra" / "save.go").unlink()
    dispatch(root / "infra" / "save.go", project_root=root, db_path=graph, include_docs=False)

    implemented = _edges(graph, "implements")
    assert ("SQLStore", "Store") not in implemented
    assert ("SQLStore", "Closer") in implemented


def test_an_interface_method_is_neither_dead_code_nor_a_test_gap(graph):
    from graph_os.tools import graph as graph_tools

    dead = json.loads(graph_tools.cos_graph_dead_code(kind="method", top=500))["data"]["dead"]
    untested = json.loads(graph_tools.cos_graph_test_gap(kind="method", top=500))["data"]["untested"]

    abstract = "code:method:domain/store.go::Store.Get"
    assert abstract not in {item["uid"] for item in dead}
    assert abstract not in {item["uid"] for item in untested}
