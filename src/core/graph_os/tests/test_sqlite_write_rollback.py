"""A failed write must not strand an open transaction (TASK-929).

The backend connection is thread-cached and never closed, so a statement that
raises mid-write leaves sqlite3's implicit transaction open. Releasing the
in-process write lock does not end it: every other connection then blocks on
"database is locked" until the process exits — a self-deadlock that no test
caught because the failing call itself raises exactly as expected.

`in_transaction` is the discriminating assertion. A second-connection write is
NOT: under this fixture's pragmas it succeeds either way, so it would be a test
that passes without the fix and guards nothing. The cross-connection block
reproduces against the dispatcher's own `_open_conn` pragmas, not here.
"""

from __future__ import annotations

import sqlite3

import pytest

from graph_os.backends.sqlite_backend import SqliteBackend
from graph_os.types import GraphNode


@pytest.fixture()
def backend(migrated_conn):
    return SqliteBackend(conn=migrated_conn)


def _unbindable_node() -> GraphNode:
    # `label` is not a SQLite-bindable type, so execute() raises after the
    # implicit transaction has already begun.
    return GraphNode(
        uid="code:file:broken.py",
        kind="file",
        label=object(),  # type: ignore[arg-type]
        file_path="broken.py",
    )


def test_failed_upsert_node_leaves_no_open_transaction(backend, migrated_conn) -> None:
    # sqlite3.Error, not a leaf class: an unbindable parameter raises
    # InterfaceError on 3.10 and ProgrammingError on 3.11+. Which one it is has
    # no bearing on the invariant under test — that the transaction is closed.
    with pytest.raises(sqlite3.Error):
        backend.upsert_node(_unbindable_node())

    assert migrated_conn.in_transaction is False


class _LookupMissesOnce:
    # Another `graph-reindex -j N` worker inserts the same uid between this
    # writer's existence check and its INSERT — the window the proxy pins open.
    def __init__(self, conn: sqlite3.Connection, rival_write) -> None:
        self._conn = conn
        self._rival_write = rival_write
        self._fired = False

    def execute(self, sql: str, *params):
        if not self._fired and "WHERE uid = ?" in sql and sql.lstrip().startswith("SELECT id"):
            self._fired = True
            self._rival_write()
            return self._conn.execute("SELECT 1 WHERE 0")
        return self._conn.execute(sql, *params)

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


def test_upsert_node_survives_a_rival_insert_of_the_same_uid(migrated_conn) -> None:
    node = GraphNode(uid="code:file:shared.py", kind="file", label="shared.py")
    rival = SqliteBackend(conn=migrated_conn)
    racer = SqliteBackend(conn=migrated_conn)
    racer._conn = _LookupMissesOnce(migrated_conn, lambda: rival.upsert_node(node))  # type: ignore[assignment]

    node_id = racer.upsert_node(node)

    rows = migrated_conn.execute("SELECT id FROM graph_nodes WHERE uid=?", (node.uid,)).fetchall()
    assert [tuple(row) for row in rows] == [(node_id,)]


def test_a_successful_write_still_commits(backend, migrated_conn) -> None:
    node = GraphNode(uid="code:file:ok.py", kind="file", label="ok.py", file_path="ok.py")
    backend.upsert_node(node)

    assert migrated_conn.in_transaction is False
    row = migrated_conn.execute("SELECT label FROM graph_nodes WHERE uid=?", (node.uid,)).fetchone()
    assert row is not None and row[0] == "ok.py"


def test_a_stub_upsert_keeps_the_real_nodes_kind_and_label(migrated_conn) -> None:
    backend = SqliteBackend(conn=migrated_conn)
    real = GraphNode(uid="code:package:go:pkg/store", kind="module", label="store")
    backend.upsert_node(real)

    backend.upsert_node(
        GraphNode(
            uid=real.uid,
            kind="code:external",
            label="code:package:go:pkg/store",
            metadata={"stub": True},
        )
    )

    row = migrated_conn.execute(
        "SELECT kind, label FROM graph_nodes WHERE uid=?", (real.uid,)
    ).fetchone()
    assert tuple(row) == ("module", "store")


def test_a_stub_carries_the_extractor_that_minted_it():
    from graph_os.extractors import code_go

    result = code_go.extract("p/p.go", 'package p\n\nimport "fmt"\n\nfunc F() { fmt.Println() }\n')
    stub = next(n for n in result.nodes if n.uid == "code:external:fmt:Println")

    assert stub.metadata["extractor"] == "code_go@v2"
