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


def test_a_successful_write_still_commits(backend, migrated_conn) -> None:
    node = GraphNode(uid="code:file:ok.py", kind="file", label="ok.py", file_path="ok.py")
    backend.upsert_node(node)

    assert migrated_conn.in_transaction is False
    row = migrated_conn.execute("SELECT label FROM graph_nodes WHERE uid=?", (node.uid,)).fetchone()
    assert row is not None and row[0] == "ok.py"
