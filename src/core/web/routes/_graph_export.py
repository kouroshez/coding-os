"""The cached /api/graph/export endpoint.

The only route in the graph surface that carries state: a freshness signature
over the node/edge tables, a project-scoped cache key, and the tri-state query
normalisation the Hub Graph tab relies on. It changes when caching or the SPA's
export contract changes; the thin wrappers in `graph` change when the tool
surface does — which is why the two live apart.
"""

from __future__ import annotations

from fastapi import Depends, Query

from .._cache import graph_export_cache
from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import unwrap
from ._graph_shared import _tools, _unavailable, router


@router.get("/export")
def graph_export(
    format: str = Query("json"),
    root_uid: str | None = Query(None),
    edge_types: str | None = Query(None),
    max_nodes: int = Query(2000, ge=1, le=50_000),
    max_hops: int | None = Query(None, ge=1, le=16),
    include_spine: bool = Query(False),
    mode: str = Query("auto"),
    exclude_kinds: str | None = Query(None),
    scope: str = Query("neighborhood"),
    _rl=Depends(make_rate_limit_dep("graph.export")),
    _m=Depends(make_metrics_dep("graph.export")),
):
    """Export a subgraph as json | mermaid | dot."""
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    et = [e.strip() for e in edge_types.split(",") if e.strip()] if edge_types else None
    # treat empty-string root_uid as "no root" (the SPA can
    # send `root_uid=` when no root is pinned).  Otherwise the BFS
    # walks from "" → empty result.
    normalised_root = root_uid.strip() if root_uid else None
    if not normalised_root:
        normalised_root = None
    # exclude_kinds: None → built-in default; empty string → empty list
    # (caller wants no noise filter); csv → split.
    if exclude_kinds is None:
        ek: list[str] | None = None
    elif exclude_kinds == "":
        ek = []
    else:
        ek = [k.strip() for k in exclude_kinds.split(",") if k.strip()]

    # Signature-based cache: the key is (node/edge freshness signature,
    # query params). A re-index bumps the signature so callers never
    # see stale data; identical repeat requests (Graph-tab depth toggle,
    # view-mode tab swap) hit the cache and return in ~1 ms instead of
    # paying the 200-900 ms producer cost. Bypasses cleanly when the
    # signature can't be computed (DB down etc.).
    def _signature() -> int:
        # Cheap (<1 ms) probe — covers the mutation paths that matter for
        # export shape: node/edge counts and both latest updated_at values,
        # so an edge-only re-resolution also bumps the signature.
        from thinking_os.database import get_pooled_conn, resolve_db_path

        conn = get_pooled_conn(resolve_db_path())
        cur = conn.execute(
            "SELECT COALESCE(MAX(updated_at), 0), COUNT(*),"
            " (SELECT COALESCE(MAX(updated_at), 0) FROM graph_edges_v12),"
            " (SELECT COUNT(*) FROM graph_edges_v12)"
            " FROM graph_nodes"
        )
        return hash(tuple(int(v) for v in cur.fetchone()))

    # Include the active project's DB path so two projects can never share a
    # cache slot even if their (node/edge count, max updated_at) signatures
    # happen to collide — the signature scopes freshness, this scopes identity.
    from thinking_os.database import resolve_db_path

    try:
        _project_key = str(resolve_db_path())
    except Exception:
        _project_key = "__unscoped__"
    cache_key = (
        _project_key,
        format,
        normalised_root,
        tuple(et) if et else None,
        max_nodes,
        max_hops,
        include_spine,
        mode,
        tuple(ek) if ek is not None else None,
        scope,
    )

    def _produce():
        return g.cos_graph_export(
            format=format,
            root_uid=normalised_root,
            edge_types=et,
            max_nodes=max_nodes,
            max_hops=max_hops,
            include_spine=include_spine,
            mode=mode,
            exclude_kinds=ek,
            scope=scope,
        )

    result = graph_export_cache.get_or_compute(
        signature_fn=_signature,
        cache_key=cache_key,
        producer=_produce,
    )
    return unwrap(result)
