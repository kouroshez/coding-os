"""graph_os — SQLite backend: the write path.

Node and edge upserts, batch writes, and the prune-before-reindex deletes. Every
method here takes the write lock; reads live in `_sqlite_read`.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterable, Sequence
from typing import Any

from ..types import GraphEdge, GraphNode, normalize_kind
from ._sqlite_connection import _SqliteConnectionBase

logger = logging.getLogger("graph_os.backends.sqlite")


class _SqliteWriteMixin(_SqliteConnectionBase):
    """Node/edge upserts and deletes."""

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
