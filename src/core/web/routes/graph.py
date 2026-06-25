"""core.web.routes.graph — /api/graph/* HTTP wrappers for 21 cos_graph_* tools."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query

from .._cache import graph_export_cache
from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import ENVELOPE_ERROR_RESPONSES, unwrap

# Ensure core/ is on sys.path.
_CORE_DIR = Path(__file__).resolve().parents[3]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

router = APIRouter(prefix="/api/graph", tags=["graph"], responses=ENVELOPE_ERROR_RESPONSES)


def _tools():
    """Lazy import guard for graph_os tools."""
    try:
        from graph_os.tools import graph as _g  # type: ignore

        return _g
    except ImportError:
        return None


def _unavailable():
    import json

    return json.dumps(
        {
            "ok": False,
            "error": {
                "category": "unavailable",
                "retryable": False,
                "message": "graph_os package not importable; install graph_os extra",
            },
        }
    )


@router.get("/query")
def graph_query(
    q: str = Query(..., description="Natural-language query"),
    kinds: str | None = Query(None, description="Comma-separated node kinds"),
    limit: int = Query(10),
    max_hops: int = Query(2),
    confidence_min: float = Query(0.3),
    include_spine: bool = Query(False),
    _rl=Depends(make_rate_limit_dep("graph.query")),
    _m=Depends(make_metrics_dep("graph.query")),
):
    """Hybrid search over node labels + docstrings."""
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    kinds_list = [k.strip() for k in kinds.split(",") if k.strip()] if kinds else None
    result = g.cos_graph_query(
        q,
        kinds=kinds_list,
        limit=limit,
        max_hops=max_hops,
        confidence_min=confidence_min,
        include_spine=include_spine,
    )
    return unwrap(result)


@router.get("/context/{uid_or_name:path}")
def graph_context(
    uid_or_name: str,
    direction: str = Query("both"),
    depth: int = Query(1),
    include_content: bool = Query(False),
    include_evidence: bool = Query(False),
    include_spine: bool = Query(False),
    _rl=Depends(make_rate_limit_dep("graph.context")),
    _m=Depends(make_metrics_dep("graph.context")),
):
    """Return neighbourhood around a node."""
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    result = g.cos_graph_context(
        uid_or_name,
        direction=direction,
        depth=depth,
        include_content=include_content,
        include_evidence=include_evidence,
        include_spine=include_spine,
    )
    return unwrap(result)


@router.get("/impact/{uid:path}")
def graph_impact(
    uid: str,
    direction: str = Query("downstream"),
    depth: int = Query(3),
    confidence_min: float = Query(0.3),
    visit_limit: int = Query(500, ge=1, le=50_000),
    _rl=Depends(make_rate_limit_dep("graph.impact")),
    _m=Depends(make_metrics_dep("graph.impact")),
):
    """Blast-radius grouped by risk tier."""
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    result = g.cos_graph_impact(
        uid,
        direction=direction,
        depth=depth,
        confidence_min=confidence_min,
        visit_limit=visit_limit,
    )
    return unwrap(result)


@router.get("/detect-changes")
def graph_detect_changes(
    files: str | None = Query(None, description="Comma-separated file paths"),
    scope: str = Query("working"),
    analyze_downstream: bool = Query(True),
    _rl=Depends(make_rate_limit_dep("graph.detect_changes")),
    _m=Depends(make_metrics_dep("graph.detect_changes")),
):
    """Map changed files to affected symbols."""
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    files_list = [f.strip() for f in files.split(",") if f.strip()] if files else None
    result = g.cos_graph_detect_changes(
        scope=scope, files=files_list, analyze_downstream=analyze_downstream
    )
    return unwrap(result)


@router.get("/trace/{entry_uid:path}")
def graph_trace(
    entry_uid: str,
    terminals: str = Query("return,exception"),
    max_steps: int = Query(50),
    _rl=Depends(make_rate_limit_dep("graph.trace")),
    _m=Depends(make_metrics_dep("graph.trace")),
):
    """Forward execution walk from an entry point."""
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    terms = tuple(t.strip() for t in terminals.split(",") if t.strip()) or ("return", "exception")
    result = g.cos_graph_trace(entry_uid, terminals=terms, max_steps=max_steps)
    return unwrap(result)


@router.get("/similar/{uid:path}")
def graph_similar(
    uid: str,
    top_k: int = Query(5),
    confidence_min: float = Query(0.5),
    _rl=Depends(make_rate_limit_dep("graph.similar")),
    _m=Depends(make_metrics_dep("graph.similar")),
):
    """Top-K nodes most similar to uid."""
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    result = g.cos_graph_similar(uid, top_k=top_k, confidence_min=confidence_min)
    return unwrap(result)


@router.get("/references/{uid:path}")
def graph_references(
    uid: str,
    kinds: str = Query("calls,accesses_field,imports,references_doc"),
    limit: int = Query(100),
    _rl=Depends(make_rate_limit_dep("graph.references")),
    _m=Depends(make_metrics_dep("graph.references")),
):
    """Inbound references to uid."""
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    kinds_tuple = tuple(k.strip() for k in kinds.split(",") if k.strip())
    result = g.cos_graph_references(uid, kinds=kinds_tuple, limit=limit)
    return unwrap(result)


@router.get("/path")
def graph_path(
    source_uid: str = Query(...),
    target_uid: str = Query(...),
    max_hops: int = Query(5),
    _rl=Depends(make_rate_limit_dep("graph.path")),
    _m=Depends(make_metrics_dep("graph.path")),
):
    """Shortest path between two nodes."""
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    result = g.cos_graph_path(source_uid, target_uid, max_hops=max_hops)
    return unwrap(result)


@router.get("/export")
def graph_export(
    format: str = Query("json"),
    root_uid: str | None = Query(None),
    edge_types: str | None = Query(None),
    max_nodes: int = Query(2000),
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

    # Signature-based cache: the key is (max(graph_nodes.updated_at),
    # query params). A re-index bumps the signature so callers never
    # see stale data; identical repeat requests (Graph-tab depth toggle,
    # view-mode tab swap) hit the cache and return in ~1 ms instead of
    # paying the 200-900 ms producer cost. Bypasses cleanly when the
    # signature can't be computed (DB down etc.).
    def _signature() -> int:
        # Cheap (<1 ms) probe — covers the only mutation paths that
        # matter for export shape: node + edge counts and the latest
        # node updated_at. Re-index bumps all three.
        from thinking_os.database import get_pooled_conn, resolve_db_path

        conn = get_pooled_conn(resolve_db_path())
        cur = conn.execute("SELECT COALESCE(MAX(updated_at), 0) FROM graph_nodes")
        return int(cur.fetchone()[0])

    cache_key = (
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


@router.get("/rename-plan/{uid:path}")
def graph_rename_plan(
    uid: str,
    new_name: str = Query(...),
    check_strings: bool = Query(True),
    _rl=Depends(make_rate_limit_dep("graph.rename_plan")),
    _m=Depends(make_metrics_dep("graph.rename_plan")),
):
    """Plan a rename — call-sites, docs, tests, risk."""
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    result = g.cos_graph_rename_plan(uid, new_name, check_strings=check_strings)
    return unwrap(result)


@router.get("/contracts")
def graph_contracts(
    scope: str = Query("all"),
    kinds: str = Query("http,mcp,grpc,event,websocket"),
    _rl=Depends(make_rate_limit_dep("graph.contracts")),
    _m=Depends(make_metrics_dep("graph.contracts")),
):
    """Enumerate every handler declared in the graph."""
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    kinds_tuple = tuple(k.strip() for k in kinds.split(",") if k.strip())
    result = g.cos_graph_contracts(scope=scope, kinds=kinds_tuple)
    return unwrap(result)


@router.get("/communities")
def graph_communities(
    top: int = Query(50, ge=1, le=200),
    min_size: int = Query(2, ge=1, le=100),
    _rl=Depends(make_rate_limit_dep("graph.communities")),
    _m=Depends(make_metrics_dep("graph.communities")),
):
    """Louvain-detected processes for the Hub Search tab grouping (TASK-075)."""
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    return unwrap(g.cos_graph_communities(top=int(top), min_size=int(min_size)))


@router.get("/entrypoints")
def graph_entrypoints(
    top: int = Query(20, ge=1, le=200),
    kind: str = Query(""),
    min_score: float = Query(0.05, ge=0.0, le=1.0),
    _rl=Depends(make_rate_limit_dep("graph.entrypoints")),
    _m=Depends(make_metrics_dep("graph.entrypoints")),
):
    """Scored entry points for the Hub Graph tab (TASK-081)."""
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    result = g.cos_graph_entrypoints(
        top=int(top),
        kind=(kind or None),
        min_score=float(min_score),
    )
    return unwrap(result)


@router.get("/doctor")
def graph_doctor(
    _rl=Depends(make_rate_limit_dep("graph.doctor")),
    _m=Depends(make_metrics_dep("graph.doctor")),
):
    """Graph backend health snapshot — counts, freshness, backend id."""
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    return unwrap(g.cos_graph_doctor())


@router.get("/search")
def graph_search(
    q: str = Query(..., description="Natural-language query"),
    top_k: int = Query(10, ge=1, le=100),
    _rl=Depends(make_rate_limit_dep("graph.search")),
    _m=Depends(make_metrics_dep("graph.search")),
):
    """Embedding-ranked semantic search over graph nodes."""
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    return unwrap(g.cos_graph_search(q, top_k=int(top_k)))


@router.get("/resolve")
def graph_resolve(
    q: str = Query(..., description="Symbol name or description to resolve"),
    kinds: str | None = Query(None, description="Comma-separated node kinds"),
    top: int = Query(10, ge=1, le=100),
    _rl=Depends(make_rate_limit_dep("graph.resolve")),
    _m=Depends(make_metrics_dep("graph.resolve")),
):
    """Resolve a name/description to canonical node uids."""
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    kinds_list = [k.strip() for k in kinds.split(",") if k.strip()] if kinds else None
    return unwrap(g.cos_graph_resolve(q, kinds=kinds_list, top=int(top)))


@router.get("/centrality")
def graph_centrality(
    top: int = Query(20, ge=1, le=200),
    kind: str = Query(""),
    metric: str = Query("degree"),
    include_external: bool = Query(False),
    include_structural: bool = Query(False),
    _rl=Depends(make_rate_limit_dep("graph.centrality")),
    _m=Depends(make_metrics_dep("graph.centrality")),
):
    """Most-connected nodes by the chosen centrality metric."""
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    result = g.cos_graph_centrality(
        top=int(top),
        kind=(kind or None),
        metric=metric,
        include_external=include_external,
        include_structural=include_structural,
    )
    return unwrap(result)


@router.get("/ranking")
def graph_ranking(
    q: str | None = Query(None, description="Optional query to personalize ranking"),
    top: int = Query(20, ge=1, le=200),
    kind: str = Query(""),
    damping: float = Query(0.85, ge=0.0, le=1.0),
    iterations: int = Query(30, ge=1, le=200),
    include_external: bool = Query(False),
    include_tests: bool = Query(False),
    _rl=Depends(make_rate_limit_dep("graph.ranking")),
    _m=Depends(make_metrics_dep("graph.ranking")),
):
    """PageRank-style importance ranking over the graph."""
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    result = g.cos_graph_ranking(
        query=q,
        top=int(top),
        kind=(kind or None),
        damping=float(damping),
        iterations=int(iterations),
        include_external=include_external,
        include_tests=include_tests,
    )
    return unwrap(result)


@router.get("/cycles")
def graph_cycles(
    scope: str = Query("imports"),
    top: int = Query(20, ge=1, le=200),
    min_size: int = Query(2, ge=2, le=100),
    _rl=Depends(make_rate_limit_dep("graph.cycles")),
    _m=Depends(make_metrics_dep("graph.cycles")),
):
    """Dependency cycles in the chosen edge scope."""
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    result = g.cos_graph_cycles(scope=scope, top=int(top), min_size=int(min_size))
    return unwrap(result)


@router.get("/dead-code")
def graph_dead_code(
    kind: str = Query(""),
    top: int = Query(50, ge=1, le=500),
    include_tests: bool = Query(False),
    _rl=Depends(make_rate_limit_dep("graph.dead_code")),
    _m=Depends(make_metrics_dep("graph.dead_code")),
):
    """Symbols with no inbound references (candidate dead code)."""
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    result = g.cos_graph_dead_code(kind=kind, top=int(top), include_tests=include_tests)
    return unwrap(result)


@router.get("/diff")
def graph_diff(
    base: str = Query("HEAD~1"),
    head: str = Query("HEAD"),
    analyze_downstream: bool = Query(True),
    _rl=Depends(make_rate_limit_dep("graph.diff")),
    _m=Depends(make_metrics_dep("graph.diff")),
):
    """Structural diff of the graph between two git refs."""
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    result = g.cos_graph_diff(base=base, head=head, analyze_downstream=analyze_downstream)
    return unwrap(result)
