"""`implements` follows Go's method-set rules: signatures, ambiguous promotion, packages, defined types."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_go")

FILES = {
    "go.mod": "module example.com/shop\n\ngo 1.22\n",
    "kinds/ifaces.go": (
        "package kinds\n\n"
        "type Finder interface{ Find(id string) error }\n\n"
        "type Closer interface{ Close() }\n\n"
        "type Failure interface{ Error() string }\n\n"
        "type Runnable interface{ Run() }\n\n"
        "type Putter interface{ Put() }\n\n"
        "type Cache interface{ Set(key string, value any, raw []byte) error }\n"
    ),
    "kinds/types.go": (
        "package kinds\n\n"
        "type ByInt struct{}\n\nfunc (ByInt) Find(id int) error { return nil }\n\n"
        "type ByKey struct{}\n\nfunc (ByKey) Find(key string) error { return nil }\n\n"
        "type File struct{}\n\nfunc (File) Close() {}\n\n"
        "type Conn struct{}\n\nfunc (Conn) Close() {}\n\n"
        "type Both struct {\n\tFile\n\tConn\n}\n\n"
        "type Own struct {\n\tFile\n\tConn\n}\n\nfunc (Own) Close() {}\n\n"
        "type inner struct{ Conn }\n\n"
        "type Shallow struct {\n\tFile\n\tinner\n}\n\n"
        "type MyErr struct{ error }\n\n"
        "type Base struct{}\n\nfunc (Base) Run() {}\n\n"
        "type Runner Base\n\n"
        'type Store struct{}\n\nfunc (s *Store) Get() string { return "" }\n\n'
        "type Mem struct{}\n\n"
        "func (m *Mem) Set(key string, value interface{}, raw []uint8) error { return nil }\n"
    ),
    "kinds/store_ext_test.go": (
        "package kinds_test\n\ntype Store struct{}\n\nfunc (s *Store) Put() {}\n"
    ),
}


@pytest.fixture(scope="module")
def implements(tmp_path_factory: pytest.TempPathFactory) -> set[tuple[str, str]]:
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools.reindex_dispatch import dispatch

    root: Path = tmp_path_factory.mktemp("go_implements")
    (root / ".coding-os").mkdir()
    for relative, text in FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    db = str(root / "graph.db")
    for relative in FILES:
        dispatch(root / relative, project_root=root, db_path=db, include_docs=False)
    SqliteBackend(conn=init_db(db)).link_cross_file()
    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            "SELECT s.uid, t.uid FROM graph_edges_v12 e JOIN graph_nodes s ON s.id = e.source_id "
            "JOIN graph_nodes t ON t.id = e.target_id WHERE e.edge_type = 'implements'"
        ).fetchall()
    finally:
        conn.close()
    return {
        (source.removeprefix("code:class:"), target.rpartition("::")[2]) for source, target in rows
    }


def test_parameter_and_result_types_must_match_not_only_their_count(implements):
    assert ("kinds/types.go::ByKey", "Finder") in implements
    assert ("kinds/types.go::ByInt", "Finder") not in implements


def test_a_method_two_embedded_types_promote_at_one_depth_is_ambiguous(implements):
    assert ("kinds/types.go::Both", "Closer") not in implements
    assert ("kinds/types.go::Own", "Closer") in implements
    assert ("kinds/types.go::Shallow", "Closer") in implements


def test_an_embedded_error_promotes_its_error_method(implements):
    assert ("kinds/types.go::MyErr", "Failure") in implements


def test_a_defined_type_does_not_inherit_its_base_types_methods(implements):
    assert ("kinds/types.go::Base", "Runnable") in implements
    assert ("kinds/types.go::Runner", "Runnable") not in implements


def test_a_method_of_an_external_test_package_never_joins_the_packages_type(implements):
    assert ("kinds/types.go::Store", "Putter") not in implements
    assert ("kinds/store_ext_test.go::Store", "Putter") in implements


def test_builtin_type_aliases_are_the_same_type(implements):
    assert ("kinds/types.go::Mem", "Cache") in implements
