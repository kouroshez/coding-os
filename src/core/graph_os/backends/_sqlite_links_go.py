"""graph_os — SQLite backend: bind Go package stubs to the symbol the package defines.

code_go names a callee or type it cannot see in the current file
`code:external:gopkg:<dir>:<name>`: `<dir>` is the caller's own package for a
bare call, or the in-repo package an import resolved to. A Go package is one
directory, so the stub binds to the one function, method (`Type.Method`), type
or variable with that name in a file directly inside `<dir>`. Zero or several
matches — build-tagged twins, say — keep the stub; never a guess.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from ._sqlite_connection import _SqliteConnectionBase

GOPKG_PREFIX = "code:external:gopkg:"
LINKED_CONFIDENCE = 0.9
_GO_SYMBOL_KINDS = ("function", "method", "class", "variable", "interface")


class _SqliteGoLinkMixin(_SqliteConnectionBase):
    """Cross-file binding for Go packages."""

    def link_go_symbols(self, *, file_path: str | None = None) -> int:
        """Bind `gopkg` stubs to the package's own definition; return the stubs bound."""
        with self._write_lock:
            if file_path is None:
                self._drop_name_keyed_packages()
            bound = 0
            for stub_id, directory, name in self._go_stub_rows(file_path):
                target_id = self._go_symbol(directory, name)
                if target_id is None:
                    continue
                self._conn.execute(
                    "UPDATE OR IGNORE graph_edges_v12 SET target_id = ?, "
                    "confidence = MAX(confidence, ?) WHERE target_id = ?",
                    (target_id, LINKED_CONFIDENCE, stub_id),
                )
                bound += 1
            self._conn.commit()
        return bound

    def _go_stub_rows(self, file_path: str | None) -> list[tuple[int, str, str]]:
        if file_path:
            rows = self._conn.execute(
                "SELECT DISTINCT stub.id, stub.uid FROM graph_edges_v12 e "
                "JOIN graph_nodes stub ON stub.id = e.target_id "
                "JOIN graph_nodes src ON src.id = e.source_id "
                "WHERE src.file_path = ? AND stub.uid LIKE 'code:external:gopkg:%'",
                (file_path,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, uid FROM graph_nodes WHERE uid LIKE 'code:external:gopkg:%'"
            ).fetchall()
        stubs: list[tuple[int, str, str]] = []
        for stub_id, uid in rows:
            directory, _, name = str(uid)[len(GOPKG_PREFIX) :].rpartition(":")
            if directory and name:
                stubs.append((int(stub_id), directory, name))
        return stubs

    def _go_symbol(self, directory: str, name: str) -> int | None:
        prefix = "" if directory == "." else f"{directory}/"
        kind_marks = ",".join("?" * len(_GO_SYMBOL_KINDS))
        rows = self._conn.execute(
            f"SELECT id, file_path FROM graph_nodes WHERE label = ? AND lang = 'go' "
            f"AND kind IN ({kind_marks}) AND file_path LIKE ?",
            (name, *_GO_SYMBOL_KINDS, f"{prefix}%"),
        ).fetchall()
        matches = [
            int(row_id)
            for row_id, path in rows
            if PurePosixPath(str(path)).parent.as_posix() == directory
        ]
        return matches[0] if len(matches) == 1 else None

    def _drop_name_keyed_packages(self) -> None:
        # Package nodes were keyed by package name before they were keyed by
        # directory; no per-file prune owns them (no file_path), so the global
        # pass retires them once.
        self._conn.execute(
            "DELETE FROM graph_nodes WHERE uid LIKE 'code:package:go:%' "
            'AND metadata_json LIKE \'%"extractor": "code_go@v2"%\' '
            "AND metadata_json NOT LIKE '%\"directory\"%'"
        )
