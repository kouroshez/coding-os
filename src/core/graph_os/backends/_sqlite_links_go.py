"""graph_os — SQLite backend: bind Go package stubs to the symbol the package defines.

code_go names a callee or type it cannot see in the current file
`code:external:gopkg:<dir>:<name>`: `<dir>` is the caller's own package for a
bare call, or the in-repo package an import resolved to. A Go package is one
directory, so the stub binds to the one function, method (`Type.Method`), type
or variable with that name in a file directly inside `<dir>`. Zero or several
matches — build-tagged twins, say — keep the stub; never a guess. A method
reached through another file's declaration — `Type.field.Method` or
`Func().Method` — binds through that struct's `go_fields` or that function's
`go_result`.
"""

from __future__ import annotations

import json
import time
from pathlib import PurePosixPath
from typing import Any

from ._sqlite_connection import _SqliteConnectionBase

GOPKG_PREFIX = "code:external:gopkg:"
LINKED_CONFIDENCE = 0.9
_EXTRACTOR = "code_go@v2"
_GO_SYMBOL_KINDS = ("function", "method", "class", "variable", "interface")


class _SqliteGoLinkMixin(_SqliteConnectionBase):
    """Cross-file binding for Go packages."""

    def link_go_symbols(self, *, file_path: str | None = None) -> int:
        """Bind `gopkg` stubs to the package's own definition; return the stubs bound."""
        with self._write_lock:
            if file_path is None:
                self._drop_name_keyed_packages()
            bound = 0
            declared: dict[tuple[str, str, str], dict[str, Any] | None] = {}
            # The global pass looks up thousands of stubs: one scan, not one each.
            symbols = self._go_symbol_index() if file_path is None else None
            for stub_id, directory, name in self._go_stub_rows(file_path):
                target_id = self._go_symbol(directory, name, symbols)
                if target_id is None:
                    target_id = self._go_member(directory, name, declared, symbols)
                if target_id is None:
                    continue
                self._conn.execute(
                    "UPDATE OR IGNORE graph_edges_v12 SET target_id = ?, "
                    "confidence = MAX(confidence, ?) WHERE target_id = ?",
                    (target_id, LINKED_CONFIDENCE, stub_id),
                )
                # A method declared in another file than its type hangs off
                # the stub (`contains`); it belongs to the type itself.
                self._conn.execute(
                    "UPDATE OR IGNORE graph_edges_v12 SET source_id = ? WHERE source_id = ?",
                    (target_id, stub_id),
                )
                bound += 1
            self._rehang_package_methods(file_path)
            self._conn.commit()
        return bound

    def _rehang_package_methods(self, file_path: str | None) -> None:
        # Reindexing a type's own file clears the `contains` edges its methods in
        # sibling files got by the move above, and those files are not re-read:
        # hang every method of the package back on its receiver type.
        scope = "AND t.file_path = ?" if file_path else ""
        types = self._conn.execute(
            "SELECT t.id, t.label, t.file_path FROM graph_nodes t "
            f"WHERE t.lang = 'go' AND t.kind = 'class' AND t.file_path IS NOT NULL {scope}",
            (file_path,) if file_path else (),
        ).fetchall()
        now = int(time.time())
        for type_id, label, type_path in types:
            directory = PurePosixPath(str(type_path)).parent.as_posix()
            prefix = "" if directory == "." else f"{directory}/"
            for method_id, method_path in self._conn.execute(
                "SELECT id, file_path FROM graph_nodes WHERE lang = 'go' AND kind = 'method' "
                "AND file_path LIKE ? AND file_path != ? "
                "AND json_extract(metadata_json, '$.receiver') = ? "
                "AND json_extract(metadata_json, '$.abstract') IS NULL",
                (f"{prefix}%", type_path, label),
            ).fetchall():
                if PurePosixPath(str(method_path)).parent.as_posix() != directory:
                    continue
                self._conn.execute(
                    "INSERT OR IGNORE INTO graph_edges_v12 (source_id, target_id, edge_type, "
                    "confidence, extractor, source_span, created_at, updated_at) "
                    "VALUES (?, ?, 'contains', ?, ?, NULL, ?, ?)",
                    (type_id, method_id, LINKED_CONFIDENCE, _EXTRACTOR, now, now),
                )

    def _go_stub_rows(self, file_path: str | None) -> list[tuple[int, str, str]]:
        if file_path:
            rows = self._conn.execute(
                "SELECT stub.id, stub.uid FROM graph_edges_v12 e "
                "JOIN graph_nodes stub ON stub.id = e.target_id "
                "JOIN graph_nodes src ON src.id = e.source_id "
                "WHERE src.file_path = ? AND stub.uid LIKE 'code:external:gopkg:%' "
                "UNION SELECT stub.id, stub.uid FROM graph_edges_v12 e "
                "JOIN graph_nodes stub ON stub.id = e.source_id "
                "JOIN graph_nodes tgt ON tgt.id = e.target_id "
                "WHERE tgt.file_path = ? AND stub.uid LIKE 'code:external:gopkg:%'",
                (file_path, file_path),
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

    def _go_symbol_index(self) -> dict[tuple[str, str], list[int]]:
        kind_marks = ",".join("?" * len(_GO_SYMBOL_KINDS))
        index: dict[tuple[str, str], list[int]] = {}
        for row_id, label, path in self._conn.execute(
            f"SELECT id, label, file_path FROM graph_nodes WHERE lang = 'go' "
            f"AND kind IN ({kind_marks}) AND file_path IS NOT NULL",
            _GO_SYMBOL_KINDS,
        ):
            index.setdefault((PurePosixPath(str(path)).parent.as_posix(), str(label)), []).append(
                int(row_id)
            )
        return index

    def _go_symbol(
        self, directory: str, name: str, index: dict[tuple[str, str], list[int]] | None = None
    ) -> int | None:
        if index is not None:
            found = index.get((directory, name), [])
            return found[0] if len(found) == 1 else None
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

    def _go_member(
        self,
        directory: str,
        name: str,
        cache: dict[tuple[str, str, str], dict[str, Any] | None],
        index: dict[tuple[str, str], list[int]] | None,
    ) -> int | None:
        owner, _, member = name.rpartition(".")
        if owner.endswith("()"):
            type_key = self._declared_type(directory, owner[:-2], "function", cache).get("go_result")
        else:
            type_name, _, field = owner.rpartition(".")
            if not type_name or "." in type_name:
                return None
            fields = self._declared_type(directory, type_name, "class", cache).get("go_fields")
            type_key = fields.get(field) if isinstance(fields, dict) else None
        if not isinstance(type_key, str) or not type_key.startswith(GOPKG_PREFIX):
            return None
        type_directory, _, type_label = type_key[len(GOPKG_PREFIX) :].rpartition(":")
        return self._go_symbol(type_directory, f"{type_label}.{member}", index)

    def _declared_type(
        self,
        directory: str,
        label: str,
        kind: str,
        cache: dict[tuple[str, str, str], dict[str, Any] | None],
    ) -> dict[str, Any]:
        key = (directory, label, kind)
        if key not in cache:
            prefix = "" if directory == "." else f"{directory}/"
            rows = self._conn.execute(
                "SELECT file_path, metadata_json FROM graph_nodes WHERE label = ? AND lang = 'go' "
                "AND kind = ? AND file_path LIKE ?",
                (label, kind, f"{prefix}%"),
            ).fetchall()
            found = [
                json.loads(metadata or "{}")
                for path, metadata in rows
                if PurePosixPath(str(path)).parent.as_posix() == directory
            ]
            cache[key] = found[0] if len(found) == 1 else None
        return cache[key] or {}

    def _drop_name_keyed_packages(self) -> None:
        # Package nodes were keyed by package name before they were keyed by
        # directory; no per-file prune owns them (no file_path), so the global
        # pass retires them once.
        self._conn.execute(
            "DELETE FROM graph_nodes WHERE uid LIKE 'code:package:go:%' "
            'AND metadata_json LIKE \'%"extractor": "code_go@v2"%\' '
            "AND metadata_json NOT LIKE '%\"directory\"%'"
        )
