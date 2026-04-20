"""graph-os — backend Protocol + factory.

PURPOSE:  Define the contract every storage backend (SQLite fallback,
          Kuzu primary) honours so that extractors and MCP tools
          remain storage-agnostic. The factory picks a backend based
          on availability + configuration.
INPUT:    see GraphBackend.__init__ signatures (storage-specific
          kwargs are passed through get_backend).
OUTPUT:   an object satisfying the GraphBackend Protocol.
DEPENDS:  types.GraphNode / GraphEdge / EvidenceSignal.
NOTES:    Fail-loud on explicit misconfiguration (e.g. backend="kuzu"
          requested but kuzu not installed). Silent fallback would
          hide 10x latency regressions mid-session (Section 12.5 of
          the plan).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Iterable, Protocol, Sequence, runtime_checkable

from .types import EvidenceSignal, GraphEdge, GraphNode

logger = logging.getLogger("graph_os.backend")


class BackendUnavailable(RuntimeError):
    """Raised when a backend was explicitly requested but cannot load.

    PURPOSE:  Distinguish "kuzu missing on this machine" from "kuzu
              threw at runtime" — the first is deterministic, the
              second is transient and retryable.
    INPUT:    message and optional cause.
    OUTPUT:   exception instance.
    NOTES:    MCP tools translate this to fail("unavailable", ...).
    """


@runtime_checkable
class GraphBackend(Protocol):
    """Abstract storage backend for graph_nodes + graph_edges + evidence.

    PURPOSE:  Surface the minimum set of operations needed by the
              extractors (write path) and MCP tools (read path). The
              Protocol is intentionally small in I.0 — additional
              methods ship with the slice that needs them (e.g.
              vector_search lands with I.1 alongside BGE-M3).
    INPUT:    see per-method signatures.
    OUTPUT:   see per-method signatures.
    DEPENDS:  GraphNode, GraphEdge, EvidenceSignal from .types.
    NOTES:    Implementations MUST be idempotent on upsert calls
              (same uid / same edge identity tuple => no duplicate
              row). Implementations MUST honour the Section 12.6
              parity contract so both backends return identical
              results for the I.0 parity matrix.
    """

    backend_id: str

    def close(self) -> None:  # pragma: no cover - trivial
        """Release any underlying resources (connections, file handles)."""

    # Write path ------------------------------------------------------------

    def upsert_node(self, node: GraphNode) -> int:
        """Insert or update a node; return the stable integer primary key."""

    def upsert_edge(self, edge: GraphEdge) -> int:
        """Insert or update an edge + replace its evidence rows atomically.

        Evidence is replaced wholesale — not merged — because re-resolution
        is the source of truth for which signals applied on this pass.
        """

    def bulk_upsert(
        self, nodes: Iterable[GraphNode], edges: Iterable[GraphEdge]
    ) -> tuple[int, int]:
        """Batch variant: return (nodes_written, edges_written)."""

    def delete_node(self, uid: str) -> bool:
        """Remove a node by uid (cascades to edges + evidence).

        Returns True if a row existed.
        """

    # Read path -------------------------------------------------------------

    def get_node(self, uid: str) -> GraphNode | None:
        """Fetch a node by uid, or None if unknown."""

    def count_nodes(self, kind: str | None = None) -> int:
        """Total node count, optionally filtered by kind."""

    def count_edges(self, edge_type: str | None = None) -> int:
        """Total edge count, optionally filtered by edge_type."""

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
        """List edges matching the given filters, ordered by confidence DESC.

        Either source_uid or target_uid (or both) may be set; when both
        are None, returns edges globally ordered (useful for debugging
        + parity tests). include_evidence=True JOINs evidence rows
        into the returned GraphEdge.evidence tuple; default False
        keeps responses lean (Section 5.3 of the plan).
        """


# -------------------------------------------------------------------------
# Factory
# -------------------------------------------------------------------------

_BACKEND_CHOICES = ("auto", "kuzu", "sqlite")


def _resolve_backend_choice(explicit: str | None) -> str:
    """Pick a backend identifier from explicit arg > env > default=auto."""
    chosen = (
        explicit
        or os.environ.get("COS_GRAPH_BACKEND")
        or "auto"
    ).strip().lower()
    if chosen not in _BACKEND_CHOICES:
        raise ValueError(
            f"graph backend must be one of {_BACKEND_CHOICES}; got {chosen!r}"
        )
    return chosen


def get_backend(
    *,
    backend: str | None = None,
    sqlite_conn: Any = None,
    kuzu_path: str | None = None,
    **extra: Any,
) -> GraphBackend:
    """Factory — build a backend honoring the fail-loud contract.

    PURPOSE:  Select Kuzu when available and requested (or default),
              SQLite otherwise. Raise BackendUnavailable when an
              explicit choice cannot be honoured — never silently
              downgrade.
    INPUT:    backend: None|"auto"|"kuzu"|"sqlite" (explicit > env).
              sqlite_conn: pre-opened sqlite3.Connection reused from
              thinking-os (recommended) — if None, backend picks
              COS_DB_PATH via init_db.
              kuzu_path: override for the .kuzu file path.
              extra: forwarded to the backend constructor.
    OUTPUT:   a GraphBackend instance.
    DEPENDS:  .backends.sqlite_backend.SqliteBackend always; Kuzu
              optional (ImportError tolerated when auto).
    NOTES:    In I.0, auto resolves to SQLite unless Kuzu is importable
              AND the plan's kuzu_path is writable. I.1 promotes auto
              to prefer Kuzu once the migration is in place.
    """
    choice = _resolve_backend_choice(backend)

    if choice in ("kuzu", "auto"):
        try:
            from .backends.kuzu_backend import KuzuBackend  # noqa: PLC0415

            try:
                backend = KuzuBackend(path=kuzu_path, **extra)
                _record_backend_probe(backend)
                return backend
            except BackendUnavailable as exc:
                if choice == "kuzu":
                    raise
                logger.info(
                    "Kuzu backend unavailable (%s); falling back to SQLite.",
                    exc,
                )
        except ImportError as exc:
            if choice == "kuzu":
                raise BackendUnavailable(
                    "kuzu backend requested but python-kuzu is not installed; "
                    "install the graph-os extra or use backend='sqlite'."
                ) from exc
            logger.info("kuzu python package not installed; using SQLite.")

    from .backends.sqlite_backend import SqliteBackend  # noqa: PLC0415

    backend = SqliteBackend(conn=sqlite_conn, **extra)
    _record_backend_probe(backend)
    return backend


def _record_backend_probe(backend: "GraphBackend") -> None:
    """Write `.coding-os/.graph-backend.json` so doctor C19 can audit health.

    Fire-and-forget: any failure is swallowed (path missing, permission
    denied, etc.) — the probe is an observability aid, not load-bearing.
    """
    try:
        from .enterprise import write_backend_probe  # noqa: WPS433

        state_dir = os.environ.get("COS_STATE_DIR") or str(
            Path(os.environ.get("COS_PROJECT_ROOT", os.getcwd())) / ".coding-os"
        )
        write_backend_probe(state_dir, backend=backend.backend_id)
    except Exception as exc:  # noqa: BLE001 — probe must not break backend boot
        logger.debug("backend probe write skipped: %s", exc)


__all__ = ["GraphBackend", "BackendUnavailable", "get_backend"]
