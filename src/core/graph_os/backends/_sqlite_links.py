"""graph_os — SQLite backend: cross-file edge resolution.

The three passes that turn extractor-local stubs into real edges once every
file has been indexed. Separated from the plain write path because they run on
a different cadence — after a batch, not per node.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from ._sqlite_connection import _SqliteConnectionBase

logger = logging.getLogger("graph_os.backends.sqlite")


class _SqliteLinkMixin(_SqliteConnectionBase):
    """Post-index passes that resolve stubs into edges."""

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
            for label, candidate_stubs in stubs_by_label.items():
                real_candidates = real_by_label.get(label, [])
                if not real_candidates:
                    continue
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
                f"SELECT id, metadata_json FROM graph_nodes WHERE kind = 'import_'{scope}",
                params,
            ).fetchall()
            wanted: dict[str, list[tuple[int, str]]] = {}
            for node_id, metadata_json in rows:
                try:
                    metadata = json.loads(metadata_json or "{}")
                except ValueError:
                    continue
                name = metadata.get("imported")
                module = metadata.get("source_module")
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
            for name, importers in wanted.items():
                candidates = real_by_label.get(name, [])
                if not candidates:
                    continue
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
