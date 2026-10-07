"""graph_os — SQLite backend: the write path.

Node and edge upserts, batch writes, and the prune-before-reindex deletes. Every
method here takes the write lock; reads live in `_sqlite_read`.
"""

from __future__ import annotations

import contextlib
import json
import logging
import sqlite3
import time
from collections.abc import Collection, Iterable, Iterator, Sequence
from typing import Any

from ..types import GraphEdge, GraphNode, normalize_kind
from ._sqlite_connection import _SqliteConnectionBase

logger = logging.getLogger("graph_os.backends.sqlite")

_NODE_ROW_SQL = (
    "SELECT id, doc_blob, signature, metadata_json, file_path, lang, "
    "content_hash, start_line, end_line, kind, label FROM graph_nodes WHERE uid = ?"
)


class _SqliteWriteMixin(_SqliteConnectionBase):
    """Node/edge upserts and deletes."""

    @contextlib.contextmanager
    def _write(self) -> Iterator[None]:
        # The connection is thread-cached and never closed, so a statement that
        # raises mid-write leaves the implicit transaction open and every other
        # connection then blocks on "database is locked" until the process dies.
        # Releasing the lock is not enough — the transaction outlives it.
        with self._write_lock:
            # The thread lock spans one process; `-j N` workers are processes.
            # Take the database's write lock before the first read, or another
            # worker writes the real node between a stub's read and its update.
            if not self._conn.in_transaction:
                try:
                    self._conn.execute("BEGIN IMMEDIATE")
                except sqlite3.OperationalError as exc:
                    # Another thread opened one on this shared connection; it serves.
                    if "within a transaction" not in str(exc):
                        raise
            try:
                yield
            except BaseException:
                with contextlib.suppress(Exception):
                    self._conn.rollback()
                raise

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
        with self._write():
            row = self._conn.execute(_NODE_ROW_SQL, (node.uid,)).fetchone()
            if row is None:
                # DO NOTHING, not a bare INSERT: a parallel `graph-reindex -j N`
                # worker can insert the same shared uid (a stub, a folder) after
                # the lookup above, and the bare INSERT failed the whole file.
                cursor = self._conn.execute(
                    """
                    INSERT INTO graph_nodes
                      (kind, label, uid, file_path, start_line, end_line,
                       signature, lang, doc_blob, ast_hash, content_hash,
                       metadata_json, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(uid) DO NOTHING
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
                if cursor.rowcount:
                    self._commit()
                    return int(cursor.lastrowid)
                row = self._conn.execute(_NODE_ROW_SQL, (node.uid,)).fetchone()

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
            kind_to_write, label_to_write = kind_value, node.label
            if incoming_is_stub and not existing_is_stub:
                # An importer's placeholder for a node another file owns must
                # not rename or re-kind it (a package became `doc_external`).
                doc_blob_to_write = existing_doc_blob
                sig_to_write = existing_signature
                meta_to_write = existing_meta_json or metadata_json
                kind_to_write, label_to_write = row[9], row[10]
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
                    kind_to_write,
                    label_to_write,
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
            self._commit()
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
        with self._write():
            source_id = self._node_id_for_uid(edge.source_uid)
            target_id = self._node_id_for_uid(edge.target_uid)
            cursor = self._conn.cursor()
            try:
                # `_write()` already holds the write lock: a deferred BEGIN would
                # read first and fail its upgrade at once under parallel writers.
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
                self._commit()
                return edge_id
            except Exception:
                self._conn.rollback()
                raise

    def bulk_upsert(
        self, nodes: Iterable[GraphNode], edges: Iterable[GraphEdge]
    ) -> tuple[int, int]:
        """Insert many nodes then many edges; return counts written.

        Two-pass so edges never reference an unknown uid, in one transaction.
        """
        with self._write():
            self._batch_depth += 1
            try:
                node_count = 0
                for node in nodes:
                    self.upsert_node(node)
                    node_count += 1
                edge_count = 0
                for edge in edges:
                    if self.upsert_edge(edge) >= 0:
                        edge_count += 1
            finally:
                self._batch_depth -= 1
            self._commit()
        return node_count, edge_count

    def _commit(self) -> None:
        if not self._batch_depth:
            self._conn.commit()

    def delete_node(self, uid: str) -> bool:
        """Remove a node; FK CASCADE removes edges + evidence."""
        with self._write():
            cursor = self._conn.execute("DELETE FROM graph_nodes WHERE uid=?", (uid,))
            self._conn.commit()
            return cursor.rowcount > 0

    def delete_nodes_for_file(
        self,
        file_path: str,
        *,
        extractors: Sequence[str] | None = None,
        keep_uids: Collection[str] = (),
    ) -> int:
        """Hard-delete a file's nodes, sparing any uid in ``keep_uids``.

        The graph mirrors HEAD-of-tree, so a symbol that left the file is gone,
        not historical (git is the record); see graph-os-authoring. A kept uid
        keeps its row id, which is what keeps other files' edges into it alive.
        """
        scope, params = _file_scope(file_path, extractors)
        with self._write():
            if keep_uids:
                rows = self._conn.execute(
                    f"SELECT id, uid FROM graph_nodes WHERE {scope}", params
                ).fetchall()
                stale_ids = [(row_id,) for row_id, uid in rows if uid not in keep_uids]
                self._conn.executemany("DELETE FROM graph_nodes WHERE id=?", stale_ids)
                deleted = len(stale_ids)
            else:
                cursor = self._conn.execute(f"DELETE FROM graph_nodes WHERE {scope}", params)
                deleted = int(cursor.rowcount or 0)
            self._conn.commit()
            if deleted:
                logger.debug("hard-deleted %d node(s) for %s", deleted, file_path)
            return deleted

    def files_depending_on(
        self,
        file_path: str,
        *,
        extractors: Sequence[str] | None = None,
        keep_uids: Collection[str] = (),
    ) -> list[str]:
        """Other files with an edge into a node of this file that the prune will delete."""
        scope, params = _file_scope(file_path, extractors)
        rows = self._conn.execute(
            "SELECT DISTINCT n.uid, s.file_path FROM graph_nodes n "
            "JOIN graph_edges_v12 e ON e.target_id = n.id "
            "JOIN graph_nodes s ON s.id = e.source_id "
            f"WHERE n.id IN (SELECT id FROM graph_nodes WHERE {scope}) "
            "AND s.file_path IS NOT NULL AND s.file_path != ?",
            (*params, file_path),
        ).fetchall()
        return sorted({str(source) for uid, source in rows if uid not in keep_uids})

    def delete_edges_from_file(
        self, file_path: str, *, extractors: Sequence[str] | None = None
    ) -> int:
        """Drop every edge sourced at the file's nodes so a re-extract can re-emit them."""
        scope, params = _file_scope(file_path, extractors)
        with self._write():
            cursor = self._conn.execute(
                "DELETE FROM graph_edges_v12 WHERE source_id IN "
                f"(SELECT id FROM graph_nodes WHERE {scope})",
                params,
            )
            self._conn.commit()
            return int(cursor.rowcount or 0)


def _file_scope(file_path: str, extractors: Sequence[str] | None) -> tuple[str, list[Any]]:
    if not extractors:
        return "file_path=?", [file_path]
    placeholders = " OR ".join(["metadata_json LIKE ?"] * len(extractors))
    params: list[Any] = [file_path]
    params.extend(f'%"extractor": "{extractor}"%' for extractor in extractors)
    return f"file_path=? AND ({placeholders})", params
