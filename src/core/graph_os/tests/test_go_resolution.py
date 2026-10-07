"""Go names resolve the way the compiler reads them: scopes, package clauses, generics, init, build tags."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("tree_sitter_go")

FILES = {
    "go.mod": "module example.com/c // Deprecated: use example.com/c2\n\ngo 1.24\n",
    "a/a.go": (
        "package a\n\n"
        'import "example.com/c/internal/httpapi"\n\n'
        "type Iface interface{ M() }\n\n"
        "type T struct{}\n\n"
        "func (T) M() {}\n\n"
        "var _ Iface = T{}\n\n"
        "func validate() error { return nil }\n\n"
        "func Process(validate func() error) error { return validate() }\n\n"
        "func Map[T any](xs []T) []T { return xs }\n\n"
        "func UseGeneric() {\n\t_ = Map[int](nil)\n\t_ = api.Wrap[string](nil)\n}\n\n"
        "func CallAPI() { api.Serve() }\n\n"
        "func init() { first() }\n\n"
        "func init() { second() }\n\n"
        "func first()  {}\n\n"
        "func second() {}\n"
    ),
    "internal/httpapi/api.go": (
        "package api\n\nfunc Serve() {}\n\nfunc Wrap[T any](xs []T) []T { return xs }\n"
    ),
    "osx/open_linux.go": "//go:build linux\n\npackage osx\n\nfunc open() {}\n",
    "osx/open_darwin.go": "package osx\n\nfunc open() {}\n",
    "osx/use.go": "package osx\n\nfunc Use() { open() }\n",
}


@pytest.fixture(scope="module")
def conn(tmp_path_factory: pytest.TempPathFactory) -> sqlite3.Connection:
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools.reindex_dispatch import dispatch

    root: Path = tmp_path_factory.mktemp("go_resolution")
    (root / ".coding-os").mkdir()
    for relative, text in FILES.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    db = str(root / "graph.db")
    for relative in FILES:
        dispatch(root / relative, project_root=root, db_path=db, include_docs=False)
    SqliteBackend(conn=init_db(db)).link_cross_file()
    return sqlite3.connect(db)


def _calls(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    return set(
        conn.execute(
            "SELECT s.uid, t.uid FROM graph_edges_v12 e JOIN graph_nodes s ON s.id = e.source_id "
            "JOIN graph_nodes t ON t.id = e.target_id WHERE e.edge_type = 'calls'"
        ).fetchall()
    )


def test_a_parameter_shadows_the_file_function_of_the_same_name(conn):
    assert (
        "code:function:a/a.go::Process",
        "code:function:a/a.go::validate",
    ) not in _calls(conn)


def test_an_explicit_generic_call_reaches_the_function(conn):
    calls = _calls(conn)
    assert ("code:function:a/a.go::UseGeneric", "code:function:a/a.go::Map") in calls
    assert (
        "code:function:a/a.go::UseGeneric",
        "code:function:internal/httpapi/api.go::Wrap",
    ) in calls


def test_a_package_is_called_by_its_package_clause_name_and_a_commented_module_line_resolves(
    conn,
):
    assert (
        "code:function:a/a.go::CallAPI",
        "code:function:internal/httpapi/api.go::Serve",
    ) in _calls(conn)


def test_each_init_is_its_own_function_and_the_blank_identifier_no_variable(conn):
    calls = _calls(conn)
    inits = {row[0] for row in conn.execute("SELECT uid FROM graph_nodes WHERE label = 'init'")}

    assert inits == {"code:function:a/a.go::init", "code:function:a/a.go::init#2"}
    assert ("code:function:a/a.go::init", "code:function:a/a.go::first") in calls
    assert ("code:function:a/a.go::init#2", "code:function:a/a.go::second") in calls
    assert not conn.execute("SELECT 1 FROM graph_nodes WHERE label = '_'").fetchone()


def test_a_call_to_a_build_tagged_twin_reaches_every_twin(conn):
    calls = _calls(conn)
    assert ("code:function:osx/use.go::Use", "code:function:osx/open_linux.go::open") in calls
    assert ("code:function:osx/use.go::Use", "code:function:osx/open_darwin.go::open") in calls


def test_a_fiber_handler_on_a_typed_local_or_a_parameter_resolves_by_its_type(tmp_path: Path):
    from graph_os.extractors import code_go

    source = (
        "package web\n\n"
        'import "github.com/gofiber/fiber/v2"\n\n'
        "type Users struct{}\n\n"
        "func (u *Users) List(c *fiber.Ctx) error { return nil }\n\n"
        "func h(c *fiber.Ctx) error { return nil }\n\n"
        "func Register(app *fiber.App, h fiber.Handler) {\n"
        "\tusers := &Users{}\n"
        '\tapp.Get("/users", users.List)\n'
        '\tapp.Get("/other", h)\n'
        "}\n"
    )
    handlers = {
        (edge.source_uid, edge.target_uid)
        for edge in code_go.extract("web/routes.go", source).edges
        if edge.edge_type == "calls" and edge.source_uid.startswith("cos:route:")
    }

    assert any(target.endswith("Users.List") for _, target in handlers)
    assert not any(target == "code:function:web/routes.go::h" for _, target in handlers)


def test_a_generator_file_and_a_later_local_neither_hide_the_real_callee(tmp_path: Path):
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools.reindex_dispatch import dispatch

    files = {
        "go.mod": "module example.com/g\n\ngo 1.24\n",
        "lib/gen.go": "//go:build ignore\n\npackage main\n\nfunc main() {}\n",
        "lib/lib.go": "package lib\n\nfunc Hello() {}\n",
        "app/app.go": (
            "package app\n\n"
            'import "example.com/g/lib"\n\n'
            "func client() int { return 1 }\n\n"
            "func Run() int {\n\tclient := client()\n\tlib.Hello()\n\treturn client\n}\n\n"
            "func Other(xs []func() int) {\n\t_ = client()\n"
            "\tfor _, client := range xs {\n\t\t_ = client()\n\t}\n}\n"
        ),
    }
    (tmp_path / ".coding-os").mkdir()
    for relative, text in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    db = str(tmp_path / "graph.db")
    for relative in files:
        dispatch(tmp_path / relative, project_root=tmp_path, db_path=db, include_docs=False)
    SqliteBackend(conn=init_db(db)).link_cross_file()
    calls = _calls(sqlite3.connect(db))

    assert ("code:function:app/app.go::Run", "code:function:lib/lib.go::Hello") in calls
    assert ("code:function:app/app.go::Run", "code:function:app/app.go::client") in calls
    assert ("code:function:app/app.go::Other", "code:function:app/app.go::client") in calls


def test_select_receives_switch_headers_and_interface_methods_scope_like_go(tmp_path: Path):
    from database import init_db  # type: ignore

    from graph_os.backends.sqlite_backend import SqliteBackend
    from graph_os.tools.reindex_dispatch import dispatch

    files = {
        "go.mod": "module example.com/s\n\ngo 1.24\n",
        "s/s.go": (
            "package s\n\n"
            "func v()        {}\n"
            "func c() any    { return nil }\n"
            "func client()   {}\n"
            "func Receive(ch chan func()) {\n\tselect {\n\tcase v := <-ch:\n\t\tv()\n\t}\n}\n\n"
            "func Switch() {\n\tswitch c := c().(type) {\n\tdefault:\n\t\t_ = c\n\t}\n}\n\n"
            "func Local() {\n\ttype I interface{ M(client int) }\n\tclient()\n}\n"
        ),
    }
    (tmp_path / ".coding-os").mkdir()
    for relative, text in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    db = str(tmp_path / "graph.db")
    for relative in files:
        dispatch(tmp_path / relative, project_root=tmp_path, db_path=db, include_docs=False)
    SqliteBackend(conn=init_db(db)).link_cross_file()
    calls = _calls(sqlite3.connect(db))

    assert ("code:function:s/s.go::Receive", "code:function:s/s.go::v") not in calls
    assert ("code:function:s/s.go::Switch", "code:function:s/s.go::c") in calls
    assert ("code:function:s/s.go::Local", "code:function:s/s.go::client") in calls
