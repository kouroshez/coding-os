"""graph-os — Kuzu primary backend.

PURPOSE:  Implement GraphBackend on top of Kuzu (embedded columnar
          graph DB, Cypher-capable, Apache 2.0). Primary store for
          graph walks at scale (Section 12 of the plan). I.0 provides
          the bootstrap schema + write + read parity with
          SqliteBackend. Graph-walk primitives (BFS, shortest-path,
          HNSW vector search) land in later slices.
INPUT:    a path to the .kuzu database file (defaults to
          .coding-os/graph-os.kuzu).
OUTPUT:   a GraphBackend-compatible object.
DEPENDS:  kuzu>=0.7.x (optional extra 'graph-os' in pyproject.toml).
NOTES:    Construction raises BackendUnavailable when kuzu is not
          importable OR when the path cannot be created — matches the
          fail-loud contract from Section 12.5. No silent downgrade.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..backend import BackendUnavailable
from ..types import EvidenceSignal, GraphEdge, GraphNode

logger = logging.getLogger("graph_os.backends.kuzu")

_SCHEMA_STATEMENTS = [
    # Node table — schema mirrors graph_nodes in migration v12.
    """
    CREATE NODE TABLE IF NOT EXISTS GraphNodeV12 (
      uid STRING PRIMARY KEY,
      kind STRING,
      label STRING,
      file_path STRING,
      start_line INT64,
      end_line INT64,
      signature STRING,
      lang STRING,
      doc_blob STRING,
      ast_hash STRING,
      content_hash STRING,
      metadata_json STRING,
      created_at INT64,
      updated_at INT64
    )
    """,
    # Relationship table — one per edge. The edge_type and extractor live
    # as properties so we can keep a single rel table (simpler indexing).
    """
    CREATE REL TABLE IF NOT EXISTS GraphEdgeV12 (
      FROM GraphNodeV12 TO GraphNodeV12,
      edge_type STRING,
      extractor STRING,
      confidence DOUBLE,
      source_span STRING,
      evidence_json STRING,
      created_at INT64,
      updated_at INT64
    )
    """,
]


class KuzuBackend:
    """Kuzu-backed graph store.

    PURPOSE:  Satisfy GraphBackend with Kuzu's Cypher engine. In I.0,
              graph walks still use the same shapes as SqliteBackend;
              Kuzu-native traversal ships with the slice that needs
              it (e.g. _trace in I.8).
    INPUT:    see __init__.
    OUTPUT:   see GraphBackend Protocol.
    DEPENDS:  kuzu Python package.
    NOTES:    Single-writer lock — Kuzu DB handle is not thread-safe
              for concurrent writes.
    """

    backend_id: str = "kuzu"

    def __init__(
        self,
        *,
        path: str | None = None,
        **_: Any,
    ) -> None:
        try:
            import kuzu  # type: ignore  # noqa: PLC0415
        except ImportError as exc:
            raise BackendUnavailable(
                "python-kuzu not installed; install the graph-os extra "
                "(uv sync --extra graph-os) or pass backend='sqlite'."
            ) from exc

        self._kuzu = kuzu
        resolved = path or os.environ.get(
            "COS_GRAPH_PATH", ".coding-os/graph-os.kuzu"
        )
        Path(resolved).parent.mkdir(parents=True, exist_ok=True)
        try:
            self._db = kuzu.Database(resolved)
            self._conn = kuzu.Connection(self._db)
        except Exception as exc:  # kuzu raises its own runtime errors
            raise BackendUnavailable(
                f"Kuzu failed to open database at {resolved}: {exc}"
            ) from exc
        self._write_lock = threading.Lock()
        self._bootstrap_schema()

    def _bootstrap_schema(self) -> None:
        for stmt in _SCHEMA_STATEMENTS:
            try:
                self._conn.execute(stmt)
            except Exception as exc:  # noqa: BLE001
                logger.debug("kuzu schema stmt tolerated: %s", exc)

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception as exc:  # noqa: BLE001
            logger.debug("kuzu conn close suppressed: %s", exc)

    # -- Write path --------------------------------------------------------

    def upsert_node(self, node: GraphNode) -> int:
        import json  # noqa: PLC0415

        now = int(time.time())
        metadata_json = json.dumps(node.metadata, sort_keys=True)
        params = {
            "uid": node.uid,
            "kind": node.kind,
            "label": node.label,
            "file_path": node.file_path or "",
            "start_line": node.start_line or 0,
            "end_line": node.end_line or 0,
            "signature": node.signature or "",
            "lang": node.lang or "",
            "doc_blob": node.doc_blob or "",
            "ast_hash": node.ast_hash or "",
            "content_hash": node.content_hash or "",
            "metadata_json": metadata_json,
            "created_at": now,
            "updated_at": now,
        }
        with self._write_lock:
            self._conn.execute(
                """
                MERGE (n:GraphNodeV12 {uid: $uid})
                ON CREATE SET
                  n.kind = $kind, n.label = $label,
                  n.file_path = $file_path, n.start_line = $start_line,
                  n.end_line = $end_line, n.signature = $signature,
                  n.lang = $lang, n.doc_blob = $doc_blob,
                  n.ast_hash = $ast_hash, n.content_hash = $content_hash,
                  n.metadata_json = $metadata_json,
                  n.created_at = $created_at, n.updated_at = $updated_at
                ON MATCH SET
                  n.kind = $kind, n.label = $label,
                  n.file_path = $file_path, n.start_line = $start_line,
                  n.end_line = $end_line, n.signature = $signature,
                  n.lang = $lang, n.doc_blob = $doc_blob,
                  n.ast_hash = $ast_hash, n.content_hash = $content_hash,
                  n.metadata_json = $metadata_json,
                  n.updated_at = $updated_at
                """,
                parameters=params,
            )
        return self._stable_hash_id(node.uid)

    def upsert_edge(self, edge: GraphEdge) -> int:
        import json  # noqa: PLC0415

        if self._get_node_props(edge.source_uid) is None:
            raise ValueError(
                f"unknown uid {edge.source_uid!r}: upsert the node first"
            )
        if self._get_node_props(edge.target_uid) is None:
            raise ValueError(
                f"unknown uid {edge.target_uid!r}: upsert the node first"
            )

        now = int(time.time())
        evidence_payload = json.dumps(
            [
                {
                    "signal_name": s.signal_name,
                    "weight": float(s.weight),
                    "note": s.note,
                }
                for s in edge.evidence
            ]
        )
        params = {
            "src": edge.source_uid,
            "dst": edge.target_uid,
            "edge_type": edge.edge_type,
            "extractor": edge.extractor,
            "confidence": float(edge.confidence),
            "source_span": edge.source_span or "",
            "evidence_json": evidence_payload,
            "now": now,
        }
        with self._write_lock:
            self._conn.execute(
                """
                MATCH (a:GraphNodeV12 {uid: $src}), (b:GraphNodeV12 {uid: $dst})
                OPTIONAL MATCH (a)-[r:GraphEdgeV12]->(b)
                  WHERE r.edge_type = $edge_type AND r.extractor = $extractor
                DELETE r
                """,
                parameters=params,
            )
            self._conn.execute(
                """
                MATCH (a:GraphNodeV12 {uid: $src}), (b:GraphNodeV12 {uid: $dst})
                CREATE (a)-[:GraphEdgeV12 {
                  edge_type: $edge_type,
                  extractor: $extractor,
                  confidence: $confidence,
                  source_span: $source_span,
                  evidence_json: $evidence_json,
                  created_at: $now,
                  updated_at: $now
                }]->(b)
                """,
                parameters=params,
            )
        return self._stable_hash_id(
            f"{edge.source_uid}::{edge.target_uid}::{edge.edge_type}::{edge.extractor}"
        )

    def bulk_upsert(
        self, nodes: Iterable[GraphNode], edges: Iterable[GraphEdge]
    ) -> tuple[int, int]:
        node_count = 0
        for node in nodes:
            self.upsert_node(node)
            node_count += 1
        edge_count = 0
        for edge in edges:
            self.upsert_edge(edge)
            edge_count += 1
        return node_count, edge_count

    def delete_node(self, uid: str) -> bool:
        with self._write_lock:
            result = self._conn.execute(
                "MATCH (n:GraphNodeV12 {uid: $uid}) DETACH DELETE n RETURN count(n)",
                parameters={"uid": uid},
            )
        rows = result.get_all() if hasattr(result, "get_all") else list(result)
        return bool(rows and rows[0][0] > 0)

    # -- Read path ---------------------------------------------------------

    def get_node(self, uid: str) -> GraphNode | None:
        props = self._get_node_props(uid)
        if props is None:
            return None
        return self._props_to_node(props)

    def count_nodes(self, kind: str | None = None) -> int:
        if kind is None:
            result = self._conn.execute(
                "MATCH (n:GraphNodeV12) RETURN count(n)"
            )
        else:
            result = self._conn.execute(
                "MATCH (n:GraphNodeV12) WHERE n.kind = $kind RETURN count(n)",
                parameters={"kind": kind},
            )
        rows = self._rows(result)
        return int(rows[0][0]) if rows else 0

    def count_edges(self, edge_type: str | None = None) -> int:
        if edge_type is None:
            result = self._conn.execute(
                "MATCH ()-[r:GraphEdgeV12]->() RETURN count(r)"
            )
        else:
            result = self._conn.execute(
                "MATCH ()-[r:GraphEdgeV12]->() WHERE r.edge_type = $et RETURN count(r)",
                parameters={"et": edge_type},
            )
        rows = self._rows(result)
        return int(rows[0][0]) if rows else 0

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
        import json  # noqa: PLC0415

        where = ["r.confidence >= $cmin"]
        params: dict[str, Any] = {"cmin": float(confidence_min), "lim": int(limit)}
        if source_uid is not None:
            where.append("a.uid = $src")
            params["src"] = source_uid
        if target_uid is not None:
            where.append("b.uid = $dst")
            params["dst"] = target_uid
        if edge_types:
            where.append("r.edge_type IN $types")
            params["types"] = list(edge_types)
        query = f"""
            MATCH (a:GraphNodeV12)-[r:GraphEdgeV12]->(b:GraphNodeV12)
            WHERE {' AND '.join(where)}
            RETURN a.uid, b.uid, r.edge_type, r.extractor, r.confidence,
                   r.source_span, r.evidence_json
            ORDER BY r.confidence DESC, a.uid ASC, b.uid ASC, r.edge_type ASC
            LIMIT $lim
        """
        result = self._conn.execute(query, parameters=params)
        edges: list[GraphEdge] = []
        for row in self._rows(result):
            evidence_tuple: tuple[EvidenceSignal, ...] = ()
            if include_evidence and row[6]:
                try:
                    payload = json.loads(row[6])
                    evidence_tuple = tuple(
                        EvidenceSignal(
                            signal_name=item.get("signal_name", ""),
                            weight=float(item.get("weight", 0.0)),
                            note=item.get("note"),
                        )
                        for item in payload
                    )
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    logger.debug("kuzu evidence parse failed: %s", exc)
            edges.append(
                GraphEdge(
                    source_uid=row[0],
                    target_uid=row[1],
                    edge_type=row[2],
                    extractor=row[3],
                    confidence=float(row[4]),
                    source_span=row[5] or None,
                    evidence=evidence_tuple,
                )
            )
        return edges

    # -- Internal helpers --------------------------------------------------

    def _get_node_props(self, uid: str) -> dict[str, Any] | None:
        result = self._conn.execute(
            """
            MATCH (n:GraphNodeV12 {uid: $uid})
            RETURN n.kind, n.label, n.uid, n.file_path, n.start_line,
                   n.end_line, n.signature, n.lang, n.doc_blob,
                   n.ast_hash, n.content_hash, n.metadata_json
            """,
            parameters={"uid": uid},
        )
        rows = self._rows(result)
        if not rows:
            return None
        keys = (
            "kind",
            "label",
            "uid",
            "file_path",
            "start_line",
            "end_line",
            "signature",
            "lang",
            "doc_blob",
            "ast_hash",
            "content_hash",
            "metadata_json",
        )
        return dict(zip(keys, rows[0]))

    @staticmethod
    def _props_to_node(props: dict[str, Any]) -> GraphNode:
        import json  # noqa: PLC0415

        metadata: dict[str, Any] = {}
        raw = props.get("metadata_json") or ""
        if raw:
            try:
                metadata = json.loads(raw)
            except json.JSONDecodeError as exc:
                logger.debug("kuzu node metadata decode failed: %s", exc)
        return GraphNode(
            uid=props["uid"],
            kind=props["kind"],
            label=props["label"],
            file_path=_none_if_empty(props.get("file_path")),
            start_line=_none_if_zero(props.get("start_line")),
            end_line=_none_if_zero(props.get("end_line")),
            signature=_none_if_empty(props.get("signature")),
            lang=_none_if_empty(props.get("lang")),
            doc_blob=_none_if_empty(props.get("doc_blob")),
            ast_hash=_none_if_empty(props.get("ast_hash")),
            content_hash=_none_if_empty(props.get("content_hash")),
            metadata=metadata,
        )

    @staticmethod
    def _rows(result: Any) -> list[list[Any]]:
        if hasattr(result, "get_all"):
            return list(result.get_all())
        return [list(row) for row in result]

    @staticmethod
    def _stable_hash_id(material: str) -> int:
        # Kuzu assigns its own internal ids — we return a deterministic
        # 63-bit hash of the stable identity so callers have a numeric
        # handle that survives across sessions without needing Kuzu's
        # private id. The value is cosmetic: tests should rely on uid.
        import hashlib  # noqa: PLC0415

        digest = hashlib.blake2b(material.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(digest, "big") & ((1 << 63) - 1)


def _none_if_empty(value: Any) -> str | None:
    return value if value not in (None, "", b"") else None


def _none_if_zero(value: Any) -> int | None:
    if value is None or value == 0:
        return None
    return int(value)


__all__ = ["KuzuBackend"]
