"""graph_os — backend Protocol + factory.

DEPENDS:  types.GraphNode / GraphEdge / EvidenceSignal.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Iterable, Protocol, Sequence, runtime_checkable

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

    DEPENDS:  .backends.sqlite_backend.SqliteBackend always; Kuzu
              optional (ImportError tolerated when auto).
    """
    choice = _resolve_backend_choice(backend)
    # Only the default-path case is safe to cache. Tests + explicit
    # callers that pass `sqlite_conn=` or `kuzu_path=` get a fresh
    # backend so they retain control over the underlying handle.
    cacheable = sqlite_conn is None and kuzu_path is None and not extra
    cache_key = (choice,) if cacheable else None
    if cache_key is not None:
        cached = _BACKEND_CACHE.get(cache_key)
        if cached is not None:
            return cached

    # Negative cache: once we've confirmed Kuzu is empty / unreachable in
    # this process, every subsequent `auto` call paid the probe cost
    # again (open Kuzu DB, count_nodes(), close, raise). For projects
    # whose reindexer only writes to SQLite that's the steady-state path,
    # so the probe is pure overhead. Skip straight to SQLite once we've
    # taken the verdict — explicit backend="kuzu" callers still re-probe
    # so tests / Kuzu-primary deployments behave normally.
    if choice == "auto" and _KUZU_AUTO_FALLBACK:
        from .backends.sqlite_backend import SqliteBackend  # noqa: PLC0415
        backend = SqliteBackend(conn=sqlite_conn, **extra)
        _record_backend_probe(backend)
        if cache_key is not None:
            _BACKEND_CACHE[cache_key] = backend
        return backend

    if choice in ("kuzu", "auto"):
        try:
            from .backends.kuzu_backend import KuzuBackend  # noqa: PLC0415

            try:
                backend = KuzuBackend(path=kuzu_path, **extra)
                # `auto` falls back to SQLite when Kuzu is reachable
                # but empty — that's the common state for projects
                # whose reindexer only writes to SQLite. An explicit
                # backend="kuzu" caller stays on Kuzu (for tests +
                # eventual Kuzu-primary deployments).
                if choice == "auto":
                    try:
                        if backend.count_nodes() == 0:
                            logger.info(
                                "Kuzu backend opened but empty; "
                                "falling back to SQLite for `auto`.",
                            )
                            try:
                                backend.close()
                            except Exception as exc:  # noqa: BLE001
                                logger.debug(
                                    "kuzu close after empty probe failed: %s",
                                    exc,
                                )
                            raise BackendUnavailable("kuzu_empty")
                    except BackendUnavailable:
                        raise
                    except Exception as exc:  # noqa: BLE001
                        logger.debug("kuzu probe failed: %s", exc)
                _record_backend_probe(backend)
                if cache_key is not None:
                    _BACKEND_CACHE[cache_key] = backend
                return backend
            except BackendUnavailable as exc:
                if choice == "kuzu":
                    raise
                logger.info(
                    "Kuzu backend unavailable (%s); falling back to SQLite.",
                    exc,
                )
                _set_kuzu_auto_fallback()
        except ImportError as exc:
            if choice == "kuzu":
                raise BackendUnavailable(
                    "kuzu backend requested but python-kuzu is not installed; "
                    "install the graph_os extra or use backend='sqlite'."
                ) from exc
            logger.info("kuzu python package not installed; using SQLite.")
            _set_kuzu_auto_fallback()

    from .backends.sqlite_backend import SqliteBackend  # noqa: PLC0415

    backend = SqliteBackend(conn=sqlite_conn, **extra)
    _record_backend_probe(backend)
    if cache_key is not None:
        _BACKEND_CACHE[cache_key] = backend
    return backend


# Per-process cache of backend instances. Sized to one or two entries
# in practice (default + maybe an explicit kuzu_path).
_BACKEND_CACHE: dict[Any, "GraphBackend"] = {}

# Negative cache flag — set the first time `auto` falls back to SQLite
# because Kuzu was empty / missing / unreachable, so subsequent `auto`
# calls in the same process skip the probe entirely (each Kuzu probe
# pays an open / count / close round-trip otherwise). Cleared by
# reset_backend_cache() so tests / hot-reload scenarios re-probe.
_KUZU_AUTO_FALLBACK: bool = False


def _set_kuzu_auto_fallback() -> None:
    """Mark `auto` to bypass the Kuzu probe for the rest of the process."""
    global _KUZU_AUTO_FALLBACK
    _KUZU_AUTO_FALLBACK = True


def reset_backend_cache() -> None:
    """Drop the cached backend(s).

    Tests + the dispatcher worker call this after wiping the DB so
    the next get_backend() opens a fresh connection.
    """
    global _KUZU_AUTO_FALLBACK
    _KUZU_AUTO_FALLBACK = False
    while _BACKEND_CACHE:
        _, backend = _BACKEND_CACHE.popitem()
        close = getattr(backend, "close", None)
        if callable(close):
            try:
                close()
            except Exception as exc:  # noqa: BLE001
                logger.debug("backend close suppressed: %s", exc)


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


__all__ = [
    "GraphBackend",
    "BackendUnavailable",
    "get_backend",
    "reset_backend_cache",
]
