"""graph_os — backend Protocol + factory.

DEPENDS:  types.GraphNode / GraphEdge / EvidenceSignal.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .types import EvidenceSignal, GraphEdge, GraphNode

logger = logging.getLogger("graph_os.backend")


class BackendUnavailable(RuntimeError):
    """Raised when a backend was explicitly requested but cannot load."""


@runtime_checkable
class GraphBackend(Protocol):
    """Abstract storage backend for graph_nodes + graph_edges + evidence.

    DEPENDS:  GraphNode, GraphEdge, EvidenceSignal from .types.
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

    def get_nodes_bulk(self, uids: Sequence[str]) -> dict[str, GraphNode]:
        """B6: batch variant — single query, returns ``{uid: GraphNode}``.

        Missing uids simply do not appear in the mapping. Implementations
        MUST return a fresh dict each call so callers can mutate safely.
        This is the N+1 fix for ``_walk_bfs`` frontier expansion.
        """

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

    def sample_nodes(self, kind: str | None, limit: int) -> list[GraphNode]:
        """B13: return up to `limit` nodes, optionally filtered by kind."""


# -------------------------------------------------------------------------
# Factory
# -------------------------------------------------------------------------

_BACKEND_CHOICES = ("auto", "sqlite")

# Per-process gate so the "kuzu→sqlite coercion" log fires once, not on
# every request a Hub-style long-running process makes.
_KUZU_COERCE_LOGGED: bool = False


def _resolve_backend_choice(explicit: str | None) -> str:
    """Pick a backend identifier from explicit arg > env > default=auto.

    Legacy "kuzu" value is accepted and silently coerced to "sqlite" so
    pinned consumer configs from before the 2026-05-18 Kuzu retirement
    keep working.
    """
    chosen = (explicit or os.environ.get("COS_GRAPH_BACKEND") or "auto").strip().lower()
    if chosen == "kuzu":
        # Log once per process — long-running Hub callers shouldn't
        # produce a line per request after the first.
        global _KUZU_COERCE_LOGGED
        if not _KUZU_COERCE_LOGGED:
            logger.info("backend='kuzu' is retired; coercing to 'sqlite'.")
            _KUZU_COERCE_LOGGED = True
        chosen = "sqlite"
    if chosen not in _BACKEND_CHOICES:
        raise ValueError(f"graph backend must be one of {_BACKEND_CHOICES}; got {chosen!r}")
    return chosen


def get_backend(
    *,
    backend: str | None = None,
    sqlite_conn: Any = None,
    **extra: Any,
) -> GraphBackend:
    """Factory — build a backend honoring the fail-loud contract.

    DEPENDS: .backends.sqlite_backend.SqliteBackend (the only backend
    after 2026-05-18). `kuzu_path=` kwarg is accepted-and-ignored for
    one release so callers using the old signature don't break.
    """
    # Tolerate the retired `kuzu_path` kwarg so older callers don't crash
    # while we sweep call sites — but emit a DeprecationWarning so the
    # caller is told to drop it before the next release removes the
    # tolerance entirely.
    if "kuzu_path" in extra:
        import warnings

        warnings.warn(
            "get_backend(kuzu_path=…) is retired (Kuzu backend removed "
            "2026-05-18); the argument is ignored and will become a "
            "TypeError in the next release.",
            DeprecationWarning,
            stacklevel=2,
        )
        extra.pop("kuzu_path", None)

    choice = _resolve_backend_choice(backend)
    # Only the default-path case is safe to cache. Tests + explicit
    # callers that pass `sqlite_conn=` get a fresh backend so they
    # retain control over the underlying handle.
    cacheable = sqlite_conn is None and not extra
    cache_db_key: str = "__default__"
    if cacheable:
        try:
            from thinking_os.database import resolve_db_path  # type: ignore

            cache_db_key = str(resolve_db_path())
        except Exception as exc:
            from core.logging_os import swallow_safe

            swallow_safe("graph_os.backend", "db path resolve for cache key failed", exc=exc)
    cache_key = (choice, cache_db_key) if cacheable else None
    if cache_key is not None:
        cached = _BACKEND_CACHE.get(cache_key)
        if cached is not None:
            return cached

    from .backends.sqlite_backend import SqliteBackend

    new_backend = SqliteBackend(conn=sqlite_conn, **extra)
    _record_backend_probe(new_backend)
    if cache_key is not None:
        _BACKEND_CACHE[cache_key] = new_backend
    return new_backend


# Per-process cache of backend instances. Sized to one or two entries
# in practice (default + maybe an explicit kuzu_path).
_BACKEND_CACHE: dict[Any, GraphBackend] = {}


def reset_backend_cache() -> None:
    """Drop the cached backend(s).

    Tests + the dispatcher worker call this after wiping the DB so
    the next get_backend() opens a fresh connection.
    """
    while _BACKEND_CACHE:
        _, backend = _BACKEND_CACHE.popitem()
        close = getattr(backend, "close", None)
        if callable(close):
            try:
                close()
            except Exception as exc:
                logger.debug("backend close suppressed: %s", exc)


def _record_backend_probe(backend: GraphBackend) -> None:
    """Write `.coding-os/.graph-backend.json` so doctor C19 can audit health.

    Fire-and-forget: any failure is swallowed (path missing, permission
    denied, etc.) — the probe is an observability aid, not load-bearing.
    """
    try:
        from .enterprise import write_backend_probe

        state_dir = os.environ.get("COS_STATE_DIR") or str(
            Path(os.environ.get("COS_PROJECT_ROOT", os.getcwd())) / ".coding-os"
        )
        write_backend_probe(state_dir, backend=backend.backend_id)
    except Exception as exc:
        logger.debug("backend probe write skipped: %s", exc)


__all__ = [
    "BackendUnavailable",
    "GraphBackend",
    "get_backend",
    "reset_backend_cache",
]
