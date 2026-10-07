"""graph_os — SQLite backend: cross-file edge resolution.

The passes that turn extractor-local stubs into real edges once every file has
been indexed (TS/JS binding lives in `_sqlite_links_ts`, Go in `_go`, shell in `_sh`). Separated from the plain write path because they run on
a different cadence — after a batch, not per node.
"""

from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any

from ._sqlite_connection import _SqliteConnectionBase

# `pkg/__init__.py: from .impl import compute` — a facade names, not defines.
FACADE_HOPS = 4
_PYTHON_SYMBOL_KINDS = ("function", "class", "variable", "interface")
_FacadeCache = dict[tuple[str, str], tuple[int, str] | None]

logger = logging.getLogger("graph_os.backends.sqlite")


class _SqliteLinkMixin(_SqliteConnectionBase):
    """Post-index passes that resolve stubs into edges."""

    def link_cross_file(self, *, file_path: str | None = None) -> dict[str, int]:
        """Run every cross-file link pass — for one file's stubs, or the whole graph."""
        counts = {
            "python_stubs": self.link_external_stubs(file_path=file_path),
            "python_imports": self.link_import_bindings(file_path=file_path),
            "python_modules": self.link_python_modules(file_path=file_path),
            # After the three above: a base class must be linked before it is walked.
            "python_inherited": self.link_python_inherited_calls(file_path=file_path),  # type: ignore[attr-defined]
            "ts_symbols": self.link_ts_symbols(file_path=file_path),  # type: ignore[attr-defined]
            "go_symbols": self.link_go_symbols(file_path=file_path),  # type: ignore[attr-defined]
            # After go_symbols: a method declared apart from its type must hang off it first.
            "go_implements": self.link_go_implements(file_path=file_path),  # type: ignore[attr-defined]
            "shell_functions": self.link_shell_functions(file_path=file_path),  # type: ignore[attr-defined]
            # Global on purpose: a prefix edited in one file moves routes in others.
            "fastapi_routes": self.link_fastapi_routes(),  # type: ignore[attr-defined]
        }
        if file_path is None or file_path.endswith(".php"):
            counts["php_handlers"] = self.link_php_handlers()
        return counts

    def link_external_stubs(self, *, file_path: str | None = None) -> int:
        with self._write_lock:
            if file_path:
                stub_rows = self._conn.execute(
                    """
                    SELECT DISTINCT stub.id, stub.uid
                    FROM graph_edges_v12 e
                    JOIN graph_nodes stub ON stub.id = e.target_id
                    JOIN graph_nodes src ON src.id = e.source_id
                    WHERE src.file_path = ?
                      AND stub.uid LIKE 'code:external:%'
                      AND stub.uid NOT LIKE 'code:external:unresolved:%'
                    """,
                    (file_path,),
                ).fetchall()
            else:
                stub_rows = self._conn.execute(
                    """
                    SELECT id, uid FROM graph_nodes
                    WHERE uid LIKE 'code:external:%'
                      AND uid NOT LIKE 'code:external:unresolved:%'
                    """
                ).fetchall()

            stubs_by_label: dict[str, list[tuple[int, str, str]]] = {}
            for stub_id, stub_uid in stub_rows:
                rest = stub_uid[len("code:external:") :]
                module, _, name = rest.rpartition(":")
                if not module or not name:
                    continue
                stubs_by_label.setdefault(name, []).append((int(stub_id), module, stub_uid))

            if not stubs_by_label:
                return 0

            labels = list(stubs_by_label.keys())
            placeholders = ",".join(["?"] * len(labels))
            real_rows = self._conn.execute(
                f"""
                SELECT id, label, file_path, kind FROM graph_nodes
                WHERE kind IN ('function','method','class','variable','interface')
                  AND label IN ({placeholders})
                  AND file_path IS NOT NULL
                """,
                tuple(labels),
            ).fetchall()
            real_by_label: dict[str, list[tuple[int, str, str]]] = {}
            for real_id, real_label, real_file, real_kind in real_rows:
                real_by_label.setdefault(real_label, []).append(
                    (int(real_id), real_file, str(real_kind))
                )

            rewrites = 0
            facades: _FacadeCache = {}
            for label, candidate_stubs in stubs_by_label.items():
                real_candidates = real_by_label.get(label, [])
                for stub_id, module, _stub_uid in candidate_stubs:
                    module_suffix = module.replace(".", "/")
                    # collect ALL real files whose path matches the
                    # stub's module, then resolve ONLY when exactly one does.
                    # First-match-break used to pick an arbitrary candidate
                    # when several `label`s exist in different modules (e.g. 3
                    # `fail` functions) — a false-edge risk amplified once the
                    # global cross-file pass runs. Ambiguous (>1) ⇒ skip, never
                    # guess.
                    matches = [
                        (real_id, real_kind)
                        for real_id, real_file, real_kind in real_candidates
                        if (
                            real_file == f"{module_suffix}.py"
                            or real_file.endswith(f"/{module_suffix}.py")
                            or real_file == f"{module_suffix}/__init__.py"
                            or real_file.endswith(f"/{module_suffix}/__init__.py")
                        )
                    ]
                    # Dotted Python modules only: a TS stub's module is a path,
                    # and link_ts_symbols owns it.
                    if not matches and "/" not in module:
                        facade = self._through_facade(module, label, facades)
                        matches = [facade] if facade else []
                    if len(matches) != 1:
                        continue
                    matched_real_id, matched_real_kind = matches[0]
                    # N2: when stub resolves to a real CLASS node, promote
                    # any inbound `calls` edges (constructor-shaped) to
                    # `constructs`. The original extract-time gate
                    # (is_constructor_like + target.startswith('code:class:'))
                    # missed these because the stub uid was `code:external:*`
                    # at the time edges were emitted.
                    # rewrite stub→real edges with OR IGNORE. A bare
                    # UPDATE aborts the WHOLE linker pass with an IntegrityError
                    # when the rewrite would duplicate an existing edge — e.g. a
                    # caller reaches the same real symbol via two module
                    # spellings (`tools._shared:fail` + `pkg.tools._shared:fail`)
                    # so the second rewrite collides on UNIQUE(source,target,
                    # edge_type,extractor). OR IGNORE skips the (duplicate)
                    # colliding rows instead of aborting; the real edge from the
                    # first rewrite already exists, so the un-rewritten leftover
                    # row is a redundant duplicate pointing at the stub. We do
                    # NOT delete it here (a blanket DELETE on target_id risked
                    # removing rows OR IGNORE skipped for non-duplicate reasons);
                    # the stub simply retains it and surfaces as an info-level
                    # `orphaned_external_unresolved` in doctor. Net: every
                    # distinct caller reaches the real node and the pass never
                    # aborts mid-loop.
                    if matched_real_kind == "class":
                        self._conn.execute(
                            "UPDATE OR IGNORE graph_edges_v12 SET target_id = ?, "
                            "edge_type = CASE WHEN edge_type='calls' "
                            "THEN 'constructs' ELSE edge_type END "
                            "WHERE target_id = ?",
                            (matched_real_id, stub_id),
                        )
                    else:
                        self._conn.execute(
                            "UPDATE OR IGNORE graph_edges_v12 "
                            "SET target_id = ? WHERE target_id = ?",
                            (matched_real_id, stub_id),
                        )
                    rewrites += 1
            self._conn.commit()
            return rewrites

    def link_import_bindings(self, *, file_path: str | None = None) -> int:
        """Bind ``import_`` nodes to the symbol they import (TASK-402).

        code_python emits one ``code:import:<file>::<name>`` node per
        imported name (metadata carries ``imported`` + ``source_module``)
        but no edge to the symbol itself, so every ``from M import name``
        caller was invisible to references/impact (init_db probe: 16 of
        ~106 caller files reachable). Same exactly-one resolution contract
        as link_external_stubs: ambiguous or unresolved → skip, never guess.
        """
        with self._write_lock:
            scope = " AND file_path = ?" if file_path else ""
            params: tuple[Any, ...] = (file_path,) if file_path else ()
            rows = self._conn.execute(
                "SELECT id, metadata_json FROM graph_nodes "
                f"WHERE kind = 'import_' AND COALESCE(lang, 'py') = 'py'{scope}",
                params,
            ).fetchall()
            wanted: dict[str, list[tuple[int, str]]] = {}
            for node_id, metadata_json in rows:
                try:
                    metadata = json.loads(metadata_json or "{}")
                except ValueError:
                    continue
                name = metadata.get("imported")
                # Absolute even for `from .x import y` — the raw relative
                # source (`..x` → `//x`) could never match a file.
                module = metadata.get("resolved_module") or metadata.get("source_module")
                if not name or not module or metadata.get("wildcard"):
                    continue
                wanted.setdefault(str(name), []).append((int(node_id), str(module)))
            if not wanted:
                return 0
            placeholders = ",".join("?" * len(wanted))
            real_rows = self._conn.execute(
                f"""
                SELECT id, label, file_path FROM graph_nodes
                WHERE kind IN ('function','class','variable','interface')
                  AND label IN ({placeholders})
                  AND file_path IS NOT NULL
                """,
                tuple(wanted),
            ).fetchall()
            real_by_label: dict[str, list[tuple[int, str]]] = {}
            for real_id, real_label, real_file in real_rows:
                real_by_label.setdefault(str(real_label), []).append((int(real_id), real_file))
            now = int(time.time())
            linked = 0
            facades: _FacadeCache = {}
            for name, importers in wanted.items():
                candidates = real_by_label.get(name, [])
                for import_id, module in importers:
                    module_suffix = module.replace(".", "/")
                    matches = {
                        real_id
                        for real_id, real_file in candidates
                        if (
                            real_file == f"{module_suffix}.py"
                            or real_file.endswith(f"/{module_suffix}.py")
                            or real_file == f"{module_suffix}/__init__.py"
                            or real_file.endswith(f"/{module_suffix}/__init__.py")
                        )
                    }
                    if not matches:
                        facade = self._through_facade(module, name, facades)
                        matches = {facade[0]} if facade else set()
                    if len(matches) != 1:
                        continue
                    cursor = self._conn.execute(
                        """
                        INSERT OR IGNORE INTO graph_edges_v12
                          (source_id, target_id, edge_type, confidence,
                           extractor, source_span, created_at, updated_at)
                        VALUES (?, ?, 'imports', 0.85, 'import_linker@v1', NULL, ?, ?)
                        """,
                        (import_id, next(iter(matches)), now, now),
                    )
                    linked += int(cursor.rowcount or 0)
            self._conn.commit()
            return linked

    def _through_facade(
        self, module: str, name: str, cache: _FacadeCache
    ) -> tuple[int, str] | None:
        key = (module, name)
        if key not in cache:
            cache[key] = None
            for _ in range(FACADE_HOPS):
                module_file = self._python_module_file(module)
                if module_file is None:
                    break
                symbol = self._python_symbol(module_file, name)
                if symbol is not None:
                    cache[key] = symbol
                    break
                row = self._conn.execute(
                    "SELECT metadata_json FROM graph_nodes WHERE uid = ?",
                    (f"code:import:{module_file}::{name}",),
                ).fetchone()
                metadata = json.loads(row[0] or "{}") if row else {}
                module = str(metadata.get("resolved_module") or metadata.get("source_module") or "")
                name = str(metadata.get("imported") or "")
                if not module or not name:
                    break
        return cache[key]

    def _python_module_file(self, module: str) -> str | None:
        row = self._conn.execute(
            "SELECT file_path FROM graph_nodes WHERE uid = ? AND file_path IS NOT NULL",
            (f"code:module:{module}",),
        ).fetchone()
        return str(row[0]) if row else None

    def _python_symbol(self, module_file: str, name: str) -> tuple[int, str] | None:
        marks = ",".join("?" * len(_PYTHON_SYMBOL_KINDS))
        rows = self._conn.execute(
            f"SELECT id, kind FROM graph_nodes WHERE file_path = ? AND label = ? AND kind IN ({marks})",
            (module_file, name, *_PYTHON_SYMBOL_KINDS),
        ).fetchall()
        return (int(rows[0][0]), str(rows[0][1])) if len(rows) == 1 else None

    def link_python_modules(self, *, file_path: str | None = None) -> int:
        """Point Python `imports` edges at the module file they name, by dotted-path suffix."""
        with self._write_lock:
            scope = " AND src.file_path = ?" if file_path else ""
            params: tuple[Any, ...] = (file_path,) if file_path else ()
            stubs = self._conn.execute(
                "SELECT DISTINCT stub.id, stub.uid FROM graph_edges_v12 e "
                "JOIN graph_nodes stub ON stub.id = e.target_id "
                "JOIN graph_nodes src ON src.id = e.source_id "
                "WHERE e.edge_type IN ('imports', 're_exports') AND src.lang = 'py' "
                f"AND stub.uid LIKE 'code:module:%' AND stub.file_path IS NULL{scope}",
                params,
            ).fetchall()
            if not stubs:
                return 0
            by_dotted = self._python_modules_by_dotted_suffix()
            linked = 0
            for stub_id, uid in stubs:
                dotted = str(uid)[len("code:module:") :]
                # `import types` must stay the stdlib, never a repo `types.py`.
                if dotted.split(".")[0] in sys.stdlib_module_names:
                    continue
                candidates = by_dotted.get(dotted, [])
                if len(candidates) != 1:
                    continue
                self._conn.execute(
                    "UPDATE OR IGNORE graph_edges_v12 SET target_id = ? WHERE target_id = ?",
                    (candidates[0], int(stub_id)),
                )
                linked += 1
            self._conn.commit()
            return linked

    def _python_modules_by_dotted_suffix(self) -> dict[str, list[int]]:
        index: dict[str, list[int]] = {}
        rows = self._conn.execute(
            "SELECT id, file_path FROM graph_nodes "
            "WHERE kind = 'module' AND lang = 'py' AND file_path LIKE '%.py'"
        ).fetchall()
        for node_id, file_path in rows:
            parts = str(file_path)[: -len(".py")].split("/")
            if parts[-1] == "__init__":
                parts.pop()
            for start in range(len(parts)):
                index.setdefault(".".join(parts[start:]), []).append(int(node_id))
        return index

    def link_php_handlers(self) -> int:
        """Resolve Laravel controller-handler stubs to real method nodes.

        Contracts emits a route→`code:external:phproute:Ctrl.method` stub
        because the controller lives in another file. After the global walk
        every method node exists, so bind each stub to the unique
        `code:method:…::Ctrl.method` node (skip when 0 or >1 match — never
        guess). Mirrors `link_external_stubs` but for the PHP class-method
        uid shape, which the Python-`.py` matcher there does not handle.
        """
        with self._write_lock:
            stub_rows = self._conn.execute(
                "SELECT id, uid FROM graph_nodes WHERE uid LIKE 'code:external:phproute:%'"
            ).fetchall()
            rewrites = 0
            for stub_id, stub_uid in stub_rows:
                key = stub_uid[len("code:external:phproute:") :]  # Ctrl.method
                matches = self._conn.execute(
                    "SELECT id FROM graph_nodes WHERE kind='method' AND uid LIKE ?",
                    (f"%::{key}",),
                ).fetchall()
                if len(matches) != 1:
                    continue
                self._conn.execute(
                    "UPDATE OR IGNORE graph_edges_v12 SET target_id = ? WHERE target_id = ?",
                    (int(matches[0][0]), int(stub_id)),
                )
                rewrites += 1
            self._conn.commit()
            return rewrites

    # -- Read path ---------------------------------------------------------
