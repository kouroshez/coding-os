"""graph_os — SQLite fallback backend.

DEPENDS:  sqlite3 stdlib; core/thinking_os/database.py for init_db when
          path-based; core/graph_os/types.py for the value types.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from ..types import EvidenceSignal, GraphEdge, GraphNode, normalize_kind

logger = logging.getLogger("graph_os.backends.sqlite")


def _import_db_module() -> Any:
    """Return the thinking_os database module.

    Prefers the installed package path (`thinking_os.database`); falls back
    to the bare ``database`` name for environments where
    core/thinking_os/ is on sys.path directly (e.g. direct script
    invocation without editable install).
    """
    try:
        from thinking_os import database as _db  # type: ignore

        return _db
    except ImportError:
        import database as _db  # type: ignore

        return _db


class SqliteBackend:
    """SQLite-backed graph store (thinking_os DB, migration v12).

    DEPENDS:  migration v12 (graph_nodes, graph_edges_v12,
              graph_evidence_v12 tables + optional FTS5 virtual
              table).
    """

    backend_id: str = "sqlite"

    def __init__(
        self,
        *,
        conn: sqlite3.Connection | None = None,
        db_path: str | None = None,
    ) -> None:
        self._owns_conn = False
        # B1: serialise writes across threads so sqlite3.Connection (which
        # is only cursor-safe, not write-safe under concurrent INSERT) does
        # not raise ProgrammingError. Reads fall under the same lock to
        # cover BEGIN/COMMIT boundaries in ``upsert_edge``.
        self._write_lock = threading.RLock()
        # P6: per-thread read connections. WAL allows multiple concurrent
        # readers; a single shared sqlite3.Connection serialises them
        # behind the GIL + connection mutex. Opening one connection per
        # thread (lazy) unblocks true parallel reads in Hub UI + parallel
        # MCP dispatch. Track all opened conns so close() can drain them.
        self._db_path: str | None = None
        self._read_conn_pool = threading.local()
        self._all_read_conns: list[sqlite3.Connection] = []
        self._read_conn_lock = threading.Lock()
        if conn is not None:
            self._conn = conn
        else:
            try:
                from thinking_os.database import resolve_db_path  # type: ignore

                resolved = db_path or str(resolve_db_path())
            except ImportError:
                # Standalone — fall back to env var + repo-relative default.
                resolved = db_path or os.environ.get("COS_DB_PATH", ".coding-os/coding-os.db")
            Path(resolved).parent.mkdir(parents=True, exist_ok=True)
            db = _import_db_module()
            # B1: own-connection path opens with check_same_thread=False so
            # multiple MCP threads can share this backend instance. WAL +
            # busy_timeout give us concurrent readers + a writer without
            # SQLITE_BUSY spam.
            self._db_path = resolved
            self._conn = sqlite3.connect(resolved, timeout=10, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")
            self._conn.execute("PRAGMA foreign_keys = ON")
            # 30s ceiling tolerates ten concurrent dispatcher workers
            # reindexing different files at the same time without the
            # busy_timeout firing.
            self._conn.execute("PRAGMA busy_timeout = 30000")
            # G16: apply the full pragma SSOT (cache_size, mmap_size,
            # temp_store, wal_autocheckpoint) so standalone-conn bench
            # harnesses (bench/scale_500k.py, bench/viewer_fps.py) +
            # reindex_dispatch.py see the same p99 SLA the pooled path
            # does. Fail-open if helper unavailable (older DB module).
            _apply_pragmas = getattr(db, "_apply_pragmas", None)
            if callable(_apply_pragmas):
                try:
                    _apply_pragmas(self._conn)
                except Exception as exc:  # pragma: no cover — diagnostic
                    logger.debug("standalone PRAGMA application skipped: %s", exc)
            db.run_migrations(self._conn)
            self._owns_conn = True
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._verify_schema()

    def _verify_schema(self) -> None:
        db = _import_db_module()
        missing: list[str] = []
        if not db.has_graph_nodes_table(self._conn):
            missing.append("graph_nodes")
        if not db.has_graph_edges_table(self._conn):
            missing.append("graph_edges_v12")
        if not db.has_graph_evidence_table(self._conn):
            missing.append("graph_evidence_v12")
        if missing:
            raise RuntimeError(
                "SqliteBackend: required tables missing "
                f"({', '.join(missing)}). Run migrations (init_db) first."
            )

    # -- Lifecycle ---------------------------------------------------------

    def close(self) -> None:
        if self._owns_conn:
            with self._write_lock:
                try:
                    self._conn.close()
                except sqlite3.Error as exc:
                    logger.debug("sqlite close suppressed: %s", exc)
        # P6: drain per-thread read connections too.
        with self._read_conn_lock:
            for conn in self._all_read_conns:
                try:
                    conn.close()
                except sqlite3.Error as exc:
                    logger.debug("sqlite read-conn close suppressed: %s", exc)
            self._all_read_conns.clear()

    def _get_read_conn(self) -> sqlite3.Connection:
        """P6: return this thread's read-only sqlite3.Connection.

        Lazy-open per thread under WAL so concurrent get_node /
        count_edges / list_edges calls don't serialise behind the
        primary connection's GIL+mutex. Falls back to the shared
        connection when ``_db_path`` is unset (caller-provided conn
        via constructor) — tests + caller-pooled scenarios keep
        working unchanged.
        """
        if self._db_path is None:
            return self._conn
        conn = getattr(self._read_conn_pool, "conn", None)
        if conn is not None:
            return conn
        conn = sqlite3.connect(self._db_path, timeout=10, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Read connections need WAL so they see committed writes
        # immediately. Foreign keys + query_only enforce read-only
        # semantics (defence-in-depth). Cache stays modest (~2MB
        # default) so 16 threads don't multiply the 64MB primary cache.
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA query_only = ON")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 30000")
        except sqlite3.Error as exc:
            logger.debug("read-conn pragma skipped: %s", exc)
        self._read_conn_pool.conn = conn
        with self._read_conn_lock:
            self._all_read_conns.append(conn)
        return conn

    # -- Write path --------------------------------------------------------

    def upsert_node(self, node: GraphNode) -> int:
        """Insert a node or update it in place; return the primary key.

        DEPENDS:  migration v12 schema.
        """
        now = int(time.time())
        metadata_json = json.dumps(dict(node.metadata), sort_keys=True)
        # Canonicalise kind at the storage boundary (S3 NodeKind). Falls
        # back to the raw string if normalize_kind doesn't recognise the
        # form so a stray label can't kill an entire reindex run.
        try:
            kind_value = normalize_kind(node.kind).value
        except ValueError:
            kind_value = node.kind
        with self._write_lock:
            row = self._conn.execute(
                "SELECT id, doc_blob, signature, metadata_json, file_path, lang, "
                "content_hash, start_line, end_line FROM graph_nodes WHERE uid = ?",
                (node.uid,),
            ).fetchone()
            if row is None:
                cursor = self._conn.execute(
                    """
                    INSERT INTO graph_nodes
                      (kind, label, uid, file_path, start_line, end_line,
                       signature, lang, doc_blob, ast_hash, content_hash,
                       metadata_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        kind_value,
                        node.label,
                        node.uid,
                        node.file_path,
                        node.start_line,
                        node.end_line,
                        node.signature,
                        node.lang,
                        node.doc_blob,
                        node.ast_hash,
                        node.content_hash,
                        metadata_json,
                        now,
                        now,
                    ),
                )
                self._conn.commit()
                return int(cursor.lastrowid)

            node_id = int(row[0])
            existing_doc_blob = row[1]
            existing_signature = row[2]
            existing_meta_json = row[3]
            existing_file_path = row[4]
            existing_lang = row[5]
            existing_content_hash = row[6]
            existing_start_line = row[7]
            existing_end_line = row[8]
            incoming_is_stub = bool(node.metadata.get("stub")) if node.metadata else False
            existing_meta = json.loads(existing_meta_json or "{}")
            existing_is_stub = bool(existing_meta.get("stub"))

            doc_blob_to_write = node.doc_blob
            sig_to_write = node.signature
            meta_to_write = metadata_json
            if incoming_is_stub and not existing_is_stub:
                doc_blob_to_write = existing_doc_blob
                sig_to_write = existing_signature
                meta_to_write = existing_meta_json or metadata_json
            else:
                if existing_doc_blob and not node.doc_blob:
                    doc_blob_to_write = existing_doc_blob
                if existing_signature and not node.signature:
                    sig_to_write = existing_signature

            # Preserve existing non-null path/lang/hash; a path-less stub upsert must not clobber them.
            file_path_to_write = (
                node.file_path if node.file_path is not None else existing_file_path
            )
            lang_to_write = node.lang if node.lang is not None else existing_lang
            content_hash_to_write = (
                node.content_hash if node.content_hash is not None else existing_content_hash
            )
            start_line_to_write = (
                node.start_line if node.start_line is not None else existing_start_line
            )
            end_line_to_write = node.end_line if node.end_line is not None else existing_end_line

            self._conn.execute(
                """
                UPDATE graph_nodes SET
                  kind=?, label=?, file_path=?, start_line=?, end_line=?,
                  signature=?, lang=?, doc_blob=?, ast_hash=?, content_hash=?,
                  metadata_json=?, updated_at=?
                WHERE id=?
                """,
                (
                    kind_value,
                    node.label,
                    file_path_to_write,
                    start_line_to_write,
                    end_line_to_write,
                    sig_to_write,
                    lang_to_write,
                    doc_blob_to_write,
                    node.ast_hash,
                    content_hash_to_write,
                    meta_to_write,
                    now,
                    node_id,
                ),
            )
            self._conn.commit()
            return node_id

    def upsert_edge(self, edge: GraphEdge) -> int:
        """Insert or update an edge; replace evidence atomically.

        DEPENDS:  upsert_node must have been called for both endpoints.

        F12 / Audit #3: extractors occasionally emit self-loops
        (source_uid == target_uid) when an AST visitor mis-resolves
        recursion or nested attribute access. They poison call-graph
        analytics. Drop them at the backend write boundary so a single
        fix covers every extractor.
        """
        if edge.source_uid == edge.target_uid:
            logger.debug(
                "self-loop dropped at upsert_edge: uid=%s type=%s", edge.source_uid, edge.edge_type
            )
            return -1
        now = int(time.time())
        with self._write_lock:
            source_id = self._node_id_for_uid(edge.source_uid)
            target_id = self._node_id_for_uid(edge.target_uid)
            cursor = self._conn.cursor()
            try:
                cursor.execute("BEGIN")
                if edge.edge_type == "contains":
                    # Structural folder-spine edge — every extractor that
                    # touches a file re-emits the folder→file spine. Dedup on
                    # (source,target,type) IGNORING extractor; otherwise a file
                    # processed by N extractors yields N identical rows that
                    # inflate degree centrality (COUNT(e.id), not DISTINCT). W6.10.
                    row = cursor.execute(
                        """
                        SELECT id FROM graph_edges_v12
                        WHERE source_id=? AND target_id=? AND edge_type=?
                        """,
                        (source_id, target_id, edge.edge_type),
                    ).fetchone()
                else:
                    row = cursor.execute(
                        """
                        SELECT id FROM graph_edges_v12
                        WHERE source_id=? AND target_id=? AND edge_type=? AND extractor=?
                        """,
                        (source_id, target_id, edge.edge_type, edge.extractor),
                    ).fetchone()
                if row is None:
                    cursor.execute(
                        """
                        INSERT INTO graph_edges_v12
                          (source_id, target_id, edge_type, confidence,
                           extractor, source_span, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            source_id,
                            target_id,
                            edge.edge_type,
                            float(edge.confidence),
                            edge.extractor,
                            edge.source_span,
                            now,
                            now,
                        ),
                    )
                    edge_id = int(cursor.lastrowid)
                else:
                    edge_id = int(row[0])
                    cursor.execute(
                        """
                        UPDATE graph_edges_v12 SET
                          confidence=?, source_span=?, updated_at=?
                        WHERE id=?
                        """,
                        (
                            float(edge.confidence),
                            edge.source_span,
                            now,
                            edge_id,
                        ),
                    )
                    cursor.execute("DELETE FROM graph_evidence_v12 WHERE edge_id=?", (edge_id,))

                for signal in edge.evidence:
                    cursor.execute(
                        """
                        INSERT INTO graph_evidence_v12
                          (edge_id, signal_name, weight, note, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            edge_id,
                            signal.signal_name,
                            float(signal.weight),
                            signal.note,
                            now,
                        ),
                    )
                self._conn.commit()
                return edge_id
            except Exception:
                self._conn.rollback()
                raise

    def bulk_upsert(
        self, nodes: Iterable[GraphNode], edges: Iterable[GraphEdge]
    ) -> tuple[int, int]:
        """Insert many nodes then many edges; return counts written.

        Two-pass so edges never reference an unknown uid.
        """
        node_count = 0
        for node in nodes:
            self.upsert_node(node)
            node_count += 1
        edge_count = 0
        for edge in edges:
            if self.upsert_edge(edge) >= 0:
                edge_count += 1
        return node_count, edge_count

    def delete_node(self, uid: str) -> bool:
        """Remove a node; FK CASCADE removes edges + evidence."""
        with self._write_lock:
            cursor = self._conn.execute("DELETE FROM graph_nodes WHERE uid=?", (uid,))
            self._conn.commit()
            return cursor.rowcount > 0

    def delete_nodes_for_file(
        self, file_path: str, *, extractors: Sequence[str] | None = None
    ) -> int:
        """Prune nodes belonging to a single source file before reindex.

        HARD delete by design — the graph mirrors HEAD-of-tree, so a symbol
        that left the file is gone, not historical (git is the record). This
        runs on every per-file reindex (prune-before-reindex), so the graph
        keeps no deletion ledger of its own — that would be pure churn.
        Node prune here is routine and logged at debug. See graph-os-authoring.
        """
        with self._write_lock:
            if not extractors:
                cursor = self._conn.execute(
                    "DELETE FROM graph_nodes WHERE file_path=?", (file_path,)
                )
            else:
                placeholders = " OR ".join(["metadata_json LIKE ?"] * len(extractors))
                params: list[Any] = [file_path]
                for ex in extractors:
                    params.append(f'%"extractor": "{ex}"%')
                cursor = self._conn.execute(
                    f"DELETE FROM graph_nodes WHERE file_path=? AND ({placeholders})",
                    params,
                )
            self._conn.commit()
            deleted = int(cursor.rowcount or 0)
            if deleted:
                logger.debug("hard-deleted %d node(s) for %s", deleted, file_path)
            return deleted

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

    def edges_among(
        self,
        uids: Sequence[str],
        *,
        edge_types: Sequence[str] | None = None,
        exclude_edge_types: Sequence[str] = ("contains",),
        limit: int = 100_000,
    ) -> list[GraphEdge]:
        """Edges whose BOTH endpoints are inside ``uids`` — the semantic
        overlay of a subtree-scoped export (TASK-406). Chunked source-side
        IN query + in-memory target filter."""
        if not uids:
            return []
        chunk = 500
        id_to_uid: dict[int, str] = {}
        uid_list = list(dict.fromkeys(uids))
        for start in range(0, len(uid_list), chunk):
            batch = uid_list[start : start + chunk]
            for row_id, row_uid in self._conn.execute(
                f"SELECT id, uid FROM graph_nodes WHERE uid IN ({','.join('?' * len(batch))})",
                batch,
            ).fetchall():
                id_to_uid[int(row_id)] = str(row_uid)
        member_ids = list(id_to_uid)
        member_set = set(member_ids)
        excluded_types = set(exclude_edge_types or ())
        wanted_types = set(edge_types) if edge_types else None
        edges: list[GraphEdge] = []
        for start in range(0, len(member_ids), chunk):
            batch = member_ids[start : start + chunk]
            rows = self._conn.execute(
                "SELECT source_id, target_id, edge_type, extractor, confidence "
                f"FROM graph_edges_v12 WHERE source_id IN ({','.join('?' * len(batch))})",
                batch,
            ).fetchall()
            for src, tgt, edge_type, extractor, confidence in rows:
                if int(tgt) not in member_set:
                    continue
                if edge_type in excluded_types:
                    continue
                if wanted_types is not None and edge_type not in wanted_types:
                    continue
                edges.append(
                    GraphEdge(
                        source_uid=id_to_uid[int(src)],
                        target_uid=id_to_uid[int(tgt)],
                        edge_type=str(edge_type),
                        extractor=str(extractor or ""),
                        confidence=float(confidence or 0.0),
                    )
                )
                if len(edges) >= limit:
                    return edges
        return edges

    def contains_ancestors_bulk(
        self, uids: Sequence[str]
    ) -> tuple[list[GraphNode], list[GraphEdge]]:
        """Ancestor closure over ``contains`` for a uid SET — one query per
        tree level instead of one walk per node (TASK-403: the per-node
        loop cost ~12 s on a 30k-uid spine export).
        """
        if not uids:
            return [], []
        chunk = 500
        id_to_uid: dict[int, str] = {}

        def _map_ids(ids: Iterable[int]) -> None:
            pending = [i for i in ids if i not in id_to_uid]
            for start in range(0, len(pending), chunk):
                batch = pending[start : start + chunk]
                for row_id, row_uid in self._conn.execute(
                    f"SELECT id, uid FROM graph_nodes WHERE id IN ({','.join('?' * len(batch))})",
                    batch,
                ).fetchall():
                    id_to_uid[int(row_id)] = str(row_uid)

        frontier: set[int] = set()
        uid_list = list(dict.fromkeys(uids))
        for start in range(0, len(uid_list), chunk):
            batch = uid_list[start : start + chunk]
            for row_id, row_uid in self._conn.execute(
                f"SELECT id, uid FROM graph_nodes WHERE uid IN ({','.join('?' * len(batch))})",
                batch,
            ).fetchall():
                id_to_uid[int(row_id)] = str(row_uid)
                frontier.add(int(row_id))

        seen: set[int] = set(frontier)
        new_ids: set[int] = set()
        edge_rows: list[tuple[int, int, float]] = []
        for _ in range(32):  # spine depth ceiling — real trees are ≤ ~12
            if not frontier:
                break
            level_parents: set[int] = set()
            frontier_list = list(frontier)
            for start in range(0, len(frontier_list), chunk):
                batch = frontier_list[start : start + chunk]
                for src, tgt, conf in self._conn.execute(
                    "SELECT source_id, target_id, confidence FROM graph_edges_v12 "
                    f"WHERE edge_type='contains' AND target_id IN ({','.join('?' * len(batch))})",
                    batch,
                ).fetchall():
                    edge_rows.append((int(src), int(tgt), float(conf or 1.0)))
                    if int(src) not in seen:
                        level_parents.add(int(src))
            seen |= level_parents
            new_ids |= level_parents
            frontier = level_parents

        ancestor_nodes: list[GraphNode] = []
        if new_ids:
            _map_ids(new_ids)
            hydrated = self.get_nodes_bulk([id_to_uid[i] for i in new_ids if i in id_to_uid])
            ancestor_nodes = list(hydrated.values())
        spine_edges = [
            GraphEdge(
                source_uid=id_to_uid[src],
                target_uid=id_to_uid[tgt],
                edge_type="contains",
                extractor="spine_closure",
                confidence=conf,
            )
            for src, tgt, conf in edge_rows
            if src in id_to_uid and tgt in id_to_uid
        ]
        return ancestor_nodes, spine_edges

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

    def get_node(self, uid: str) -> GraphNode | None:
        # G18: pure-SELECT, no write_lock — WAL gives concurrent
        # readers; the lock here was serialising reads behind any
        # in-flight write for no correctness benefit.
        # P6: thread-local read connection so parallel get_node calls
        # don't serialise behind the primary conn's mutex+GIL.
        row = (
            self._get_read_conn()
            .execute(
                """
            SELECT kind, label, uid, file_path, start_line, end_line,
                   signature, lang, doc_blob, ast_hash, content_hash,
                   metadata_json
            FROM graph_nodes WHERE uid=?
            """,
                (uid,),
            )
            .fetchone()
        )
        if row is None:
            return None
        return self._row_to_node(row)

    def get_nodes_bulk(self, uids: Sequence[str]) -> dict[str, GraphNode]:
        """B6: batch variant of get_node — one SELECT per call, not N."""
        if not uids:
            return {}
        uniq = list(dict.fromkeys(uids))
        result: dict[str, GraphNode] = {}
        # SQLite parameter limit is 999; chunk to stay safely under.
        chunk = 500
        # G18: pure-SELECT, no write_lock. P6: thread-local read conn.
        read_conn = self._get_read_conn()
        for start in range(0, len(uniq), chunk):
            group = uniq[start : start + chunk]
            placeholders = ",".join("?" for _ in group)
            rows = read_conn.execute(
                f"""
                SELECT kind, label, uid, file_path, start_line, end_line,
                       signature, lang, doc_blob, ast_hash, content_hash,
                       metadata_json
                FROM graph_nodes WHERE uid IN ({placeholders})
                """,
                tuple(group),
            ).fetchall()
            for row in rows:
                node = self._row_to_node(row)
                result[node.uid] = node
        return result

    def count_nodes(self, kind: str | None = None) -> int:
        # G18: pure-SELECT, no write_lock. P6: thread-local read conn.
        read_conn = self._get_read_conn()
        if kind is None:
            row = read_conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()
        else:
            # Accept legacy or canonical form; storage is canonical.
            try:
                kind_q = normalize_kind(kind).value
            except ValueError:
                kind_q = kind
            row = read_conn.execute(
                "SELECT COUNT(*) FROM graph_nodes WHERE kind=?", (kind_q,)
            ).fetchone()
        return int(row[0])

    def count_edges(self, edge_type: str | None = None) -> int:
        # G17: count DISTINCT logical edges (source, target, edge_type).
        # `list_edges` dedupes via highest-confidence subquery — match
        # that semantic here. G18: no write_lock. P6: thread-local conn.
        read_conn = self._get_read_conn()
        if edge_type is None:
            row = read_conn.execute(
                "SELECT COUNT(*) FROM (SELECT DISTINCT source_id, target_id, edge_type FROM graph_edges_v12)"
            ).fetchone()
        else:
            row = read_conn.execute(
                "SELECT COUNT(*) FROM (SELECT DISTINCT source_id, target_id, edge_type FROM graph_edges_v12 WHERE edge_type=?)",
                (edge_type,),
            ).fetchone()
        return int(row[0])

    def list_edges(
        self,
        *,
        source_uid: str | None = None,
        target_uid: str | None = None,
        edge_types: Sequence[str] | None = None,
        confidence_min: float = 0.0,
        include_evidence: bool = False,
        limit: int = 100,
    ) -> list[GraphEdge]:
        """List edges matching filters, ordered by confidence DESC, id ASC.

        Ordering on id ASC as a tie-break makes results deterministic
        — required for parity testing (Section 12.6 of the plan).
        """
        where_parts = ["e.confidence >= ?"]
        params: list[Any] = [float(confidence_min)]

        if source_uid is not None:
            where_parts.append("e.source_id = (SELECT id FROM graph_nodes WHERE uid=?)")
            params.append(source_uid)
        if target_uid is not None:
            where_parts.append("e.target_id = (SELECT id FROM graph_nodes WHERE uid=?)")
            params.append(target_uid)
        if edge_types:
            placeholders = ",".join("?" for _ in edge_types)
            where_parts.append(f"e.edge_type IN ({placeholders})")
            params.extend(edge_types)

        where_sql = " AND ".join(where_parts)
        # Dedupe across extractors: when multiple extractors emit the
        # same logical edge (source, target, edge_type), keep the
        # highest-confidence row (ties broken by lowest id) so the API
        # surface presents one row per relationship instead of N copies.
        query = f"""
            SELECT e.id, ns.uid, nt.uid, e.edge_type, e.extractor,
                   e.confidence, e.source_span
            FROM graph_edges_v12 e
            JOIN graph_nodes ns ON ns.id = e.source_id
            JOIN graph_nodes nt ON nt.id = e.target_id
            WHERE {where_sql}
              AND e.id = (
                SELECT id FROM graph_edges_v12 ee
                WHERE ee.source_id = e.source_id
                  AND ee.target_id = e.target_id
                  AND ee.edge_type = e.edge_type
                ORDER BY ee.confidence DESC, ee.id ASC
                LIMIT 1
              )
            ORDER BY e.confidence DESC, e.id ASC
            LIMIT ?
        """
        params.append(int(limit))
        # G18: pure-SELECT, no write_lock. P6: thread-local read conn.
        read_conn = self._get_read_conn()
        rows = read_conn.execute(query, params).fetchall()

        evidence_by_edge: dict[int, list[sqlite3.Row]] = {}
        if include_evidence and rows:
            ev_rows = read_conn.execute(
                """
                SELECT edge_id, signal_name, weight, note
                FROM graph_evidence_v12
                WHERE edge_id IN (%s)
                ORDER BY id ASC
                """
                % ",".join(str(int(r[0])) for r in rows)
            ).fetchall()
            for ev in ev_rows:
                evidence_by_edge.setdefault(int(ev[0]), []).append(ev)

        edges: list[GraphEdge] = []
        for edge_row in rows:
            evidence_tuple: tuple[EvidenceSignal, ...] = ()
            if include_evidence:
                ev_rows = evidence_by_edge.get(int(edge_row[0]), [])
                evidence_tuple = tuple(
                    EvidenceSignal(signal_name=r[1], weight=float(r[2]), note=r[3]) for r in ev_rows
                )
            edges.append(
                GraphEdge(
                    source_uid=edge_row[1],
                    target_uid=edge_row[2],
                    edge_type=edge_row[3],
                    extractor=edge_row[4],
                    confidence=float(edge_row[5]),
                    source_span=edge_row[6],
                    evidence=evidence_tuple,
                )
            )
        return edges

    def sample_nodes(self, kind: str | None, limit: int) -> list[GraphNode]:
        """B13: return up to `limit` nodes, optionally filtered by kind."""
        # G18: pure-SELECT, no write_lock. P6: thread-local read conn.
        read_conn = self._get_read_conn()
        if kind is None:
            rows = read_conn.execute(
                """
                SELECT kind, label, uid, file_path, start_line, end_line,
                       signature, lang, doc_blob, ast_hash, content_hash,
                       metadata_json
                FROM graph_nodes
                ORDER BY id ASC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        else:
            try:
                kind_q = normalize_kind(kind).value
            except ValueError:
                kind_q = kind
            rows = read_conn.execute(
                """
                SELECT kind, label, uid, file_path, start_line, end_line,
                       signature, lang, doc_blob, ast_hash, content_hash,
                       metadata_json
                FROM graph_nodes
                WHERE kind = ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (kind_q, int(limit)),
            ).fetchall()
        return [self._row_to_node(row) for row in rows]

    # -- Internal helpers --------------------------------------------------

    def _node_id_for_uid(self, uid: str) -> int:
        row = self._conn.execute("SELECT id FROM graph_nodes WHERE uid=?", (uid,)).fetchone()
        if row is None:
            raise ValueError(f"unknown uid {uid!r}: upsert the node before emitting edges")
        return int(row[0])

    @staticmethod
    def _row_to_node(row: Sequence[Any]) -> GraphNode:
        metadata = {}
        metadata_json = row[11]
        if metadata_json:
            try:
                metadata = json.loads(metadata_json)
            except json.JSONDecodeError as exc:
                logger.debug("metadata JSON decode failed for uid=%s: %s", row[2], exc)
        return GraphNode(
            kind=row[0],
            label=row[1],
            uid=row[2],
            file_path=row[3],
            start_line=row[4],
            end_line=row[5],
            signature=row[6],
            lang=row[7],
            doc_blob=row[8],
            ast_hash=row[9],
            content_hash=row[10],
            metadata=metadata,
        )


__all__ = ["SqliteBackend"]
