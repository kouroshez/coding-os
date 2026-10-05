"""graph_os — SQLite backend: bind TS/JS stubs to the symbol a module file exports.

code_ts keys a cross-file stub by the repo file its import resolved to
(`code:external:<path>:<name>`) and stamps each `code:import:` node with that
`resolved_module`. Both bind here to the one function, class, interface or
variable the file defines, following `re_exports` edges through barrel files.
One match per hop or the stub stays — never a guess.
"""

from __future__ import annotations

import json
import time
from typing import Any

from ._sqlite_connection import _SqliteConnectionBase

SCRIPT_SUFFIXES = (".ts", ".tsx", ".mts", ".cts", ".js", ".jsx", ".mjs", ".cjs", ".astro")
# A file that IS one component: its default export is the module itself.
COMPONENT_SUFFIXES = (".astro", ".vue", ".svelte", ".mdx")
REEXPORT_HOPS = 4
VALUE_IMPORT_CONFIDENCE = 0.85
TYPE_IMPORT_CONFIDENCE = 0.5
_SYMBOL_KINDS = ("function", "class", "interface", "variable")
_STUB_PREFIX = "code:external:"

_ExportCache = dict[tuple[str, str], tuple[int, str] | None]


class _SqliteTsLinkMixin(_SqliteConnectionBase):
    """Cross-file binding for TypeScript / JavaScript / Astro modules."""

    def link_ts_symbols(self, *, file_path: str | None = None) -> int:
        """Bind call stubs and import nodes to the exported symbol; return the bindings made."""
        exported: _ExportCache = {}
        with self._write_lock:
            rebound = self._bind_ts_stubs(file_path, exported)
            linked = self._bind_ts_import_nodes(file_path, exported)
            self._conn.commit()
        return rebound + linked

    def _bind_ts_stubs(self, file_path: str | None, exported: _ExportCache) -> int:
        rebound = 0
        for stub_id, module_path, name in self._ts_stub_rows(file_path):
            target = self._exported_symbol(module_path, name, exported)
            if target is None:
                continue
            target_id, target_kind = target
            # A call resolved to a class is a construction (`new` was implicit
            # in the stub); same promotion the Python linker applies.
            edge_type_sql = (
                "CASE WHEN edge_type='calls' THEN 'constructs' ELSE edge_type END"
                if target_kind == "class"
                else "edge_type"
            )
            self._conn.execute(
                f"UPDATE OR IGNORE graph_edges_v12 SET target_id = ?, edge_type = {edge_type_sql} "
                "WHERE target_id = ?",
                (target_id, stub_id),
            )
            rebound += 1
        return rebound

    def _bind_ts_import_nodes(self, file_path: str | None, exported: _ExportCache) -> int:
        scope = " AND file_path = ?" if file_path else ""
        params: tuple[Any, ...] = (file_path,) if file_path else ()
        rows = self._conn.execute(
            f"SELECT id, metadata_json FROM graph_nodes WHERE kind = 'import_'{scope}", params
        ).fetchall()
        now = int(time.time())
        linked = 0
        for import_id, metadata_json in rows:
            metadata = _metadata(metadata_json)
            module_path = str(metadata.get("resolved_module") or "")
            name = str(metadata.get("imported") or "")
            if not module_path.endswith(SCRIPT_SUFFIXES + COMPONENT_SUFFIXES) or name in ("", "*"):
                continue
            target = self._exported_symbol(module_path, name, exported)
            if target is None:
                continue
            confidence = (
                TYPE_IMPORT_CONFIDENCE if metadata.get("type_only") else VALUE_IMPORT_CONFIDENCE
            )
            cursor = self._conn.execute(
                "INSERT OR IGNORE INTO graph_edges_v12 (source_id, target_id, edge_type, "
                "confidence, extractor, source_span, created_at, updated_at) "
                "VALUES (?, ?, 'imports', ?, 'import_linker@v1', NULL, ?, ?)",
                (int(import_id), target[0], confidence, now, now),
            )
            linked += int(cursor.rowcount or 0)
        return linked

    def _ts_stub_rows(self, file_path: str | None) -> list[tuple[int, str, str]]:
        if file_path:
            rows = self._conn.execute(
                "SELECT DISTINCT stub.id, stub.uid FROM graph_edges_v12 e "
                "JOIN graph_nodes stub ON stub.id = e.target_id "
                "JOIN graph_nodes src ON src.id = e.source_id "
                "WHERE src.file_path = ? AND stub.uid LIKE 'code:external:%'",
                (file_path,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, uid FROM graph_nodes WHERE uid LIKE 'code:external:%'"
            ).fetchall()
        stubs: list[tuple[int, str, str]] = []
        for stub_id, uid in rows:
            module_path, _, name = str(uid)[len(_STUB_PREFIX) :].rpartition(":")
            if (
                module_path.endswith(SCRIPT_SUFFIXES + COMPONENT_SUFFIXES)
                and name
                and "." not in name
            ):
                stubs.append((int(stub_id), module_path, name))
        return stubs

    def _exported_symbol(
        self, module_path: str, name: str, exported: _ExportCache
    ) -> tuple[int, str] | None:
        key = (module_path, name)
        if key not in exported:
            exported[key] = (
                self._default_export(module_path)
                if name == "default"
                else self._walk_reexports(module_path, name)
            )
        return exported[key]

    def _default_export(self, module_path: str) -> tuple[int, str] | None:
        rows = self._conn.execute(
            "SELECT id, kind FROM graph_nodes WHERE file_path = ? "
            "AND json_extract(metadata_json, '$.default_export') = 1",
            (module_path,),
        ).fetchall()
        if len(rows) == 1:
            return int(rows[0][0]), str(rows[0][1])
        if module_path.endswith(COMPONENT_SUFFIXES):
            row = self._conn.execute(
                "SELECT id, kind FROM graph_nodes WHERE uid = ?", (f"code:module:{module_path}",)
            ).fetchone()
            return (int(row[0]), str(row[1])) if row else None
        return None

    def _walk_reexports(self, module_path: str, name: str) -> tuple[int, str] | None:
        frontier, visited = [module_path], {module_path}
        for _ in range(REEXPORT_HOPS + 1):
            matches = self._symbols_named(frontier, name)
            if matches:
                return matches[0] if len(matches) == 1 else None
            frontier = [path for path in self._reexported_files(frontier) if path not in visited]
            visited.update(frontier)
            if not frontier:
                return None
        return None

    def _symbols_named(self, file_paths: list[str], name: str) -> list[tuple[int, str]]:
        file_marks = ",".join("?" * len(file_paths))
        kind_marks = ",".join("?" * len(_SYMBOL_KINDS))
        rows = self._conn.execute(
            f"SELECT id, kind FROM graph_nodes WHERE label = ? AND kind IN ({kind_marks}) "
            f"AND file_path IN ({file_marks})",
            (name, *_SYMBOL_KINDS, *file_paths),
        ).fetchall()
        return [(int(row_id), str(kind)) for row_id, kind in rows]

    def _reexported_files(self, file_paths: list[str]) -> list[str]:
        marks = ",".join("?" * len(file_paths))
        rows = self._conn.execute(
            "SELECT DISTINCT target.file_path FROM graph_edges_v12 e "
            "JOIN graph_nodes source ON source.id = e.source_id "
            "JOIN graph_nodes target ON target.id = e.target_id "
            f"WHERE e.edge_type = 're_exports' AND source.file_path IN ({marks}) "
            "AND target.file_path IS NOT NULL",
            tuple(file_paths),
        ).fetchall()
        return [str(row[0]) for row in rows]


def _metadata(metadata_json: str | None) -> dict[str, Any]:
    try:
        data = json.loads(metadata_json or "{}")
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}
