"""core.web.routes.graph — /api/graph/* HTTP wrappers for 11 cos_graph_* tools.

PURPOSE: Expose all 11 cos_graph_* MCP tools as FastAPI endpoints so the SPA
         (S5) and external HTTP clients can call them without the MCP protocol.
INPUT:   HTTP request bodies / query params matching each tool's signature.
OUTPUT:  JSON response unwrapped from the MCP envelope ({data, meta} on 200,
         error body on 4xx/5xx).
DEPENDENCIES: fastapi, core.web._envelope, core.web._deps, core.graph_os.tools.graph.
NOTES:  All params are optional where the underlying tool has defaults.
        Comma-separated strings are used for list params (mirrors MCP conventions).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query

from .._deps import make_metrics_dep, make_rate_limit_dep
from .._envelope import unwrap

# Ensure core/ is on sys.path.
_CORE_DIR = Path(__file__).resolve().parents[3]
if str(_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(_CORE_DIR))

router = APIRouter(prefix="/api/graph", tags=["graph"])


def _tools():
    """Lazy import guard for graph_os tools.

    PURPOSE: Defer import so the web package boots even when graph_os extras
             are absent; the endpoint returns 503 in that case.
    INPUT:   none.
    OUTPUT:  graph tools module or None.
    DEPENDENCIES: graph_os.tools.graph.
    NOTES:   Called per-request; Python module cache makes this effectively free.
    """
    try:
        from graph_os.tools import graph as _g  # type: ignore
        return _g
    except ImportError:
        return None


def _unavailable():
    import json
    return json.dumps({
        "ok": False,
        "error": {
            "category": "unavailable",
            "retryable": False,
            "message": "graph_os package not importable; install graph-os extra",
        },
    })


@router.get("/query")
async def graph_query(
    q: str = Query(..., description="Natural-language query"),
    kinds: Optional[str] = Query(None, description="Comma-separated node kinds"),
    limit: int = Query(10),
    max_hops: int = Query(2),
    confidence_min: float = Query(0.3),
    include_spine: bool = Query(False),
    _rl=Depends(make_rate_limit_dep("graph.query")),
    _m=Depends(make_metrics_dep("graph.query")),
):
    """Hybrid search over node labels + docstrings.

    PURPOSE: HTTP wrapper for cos_graph_query.
    INPUT:   q, kinds (csv), limit, max_hops, confidence_min, include_spine.
    OUTPUT:  {data: {results}, meta} on 200.
    DEPENDENCIES: graph_os.tools.graph.cos_graph_query.
    NOTES:   kinds is a comma-separated string split internally.
    """
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
async def graph_context(
    uid_or_name: str,
    direction: str = Query("both"),
    depth: int = Query(1),
    include_content: bool = Query(False),
    include_evidence: bool = Query(False),
    include_spine: bool = Query(False),
    _rl=Depends(make_rate_limit_dep("graph.context")),
    _m=Depends(make_metrics_dep("graph.context")),
):
    """Return neighbourhood around a node.

    PURPOSE: HTTP wrapper for cos_graph_context.
    INPUT:   uid_or_name (path), direction, depth, include_* flags.
    OUTPUT:  {data: {node, neighbours, edges_by_type}, meta} on 200.
    DEPENDENCIES: graph_os.tools.graph.cos_graph_context.
    NOTES:   uid_or_name uses :path so colons in uids don't get mis-parsed.
    """
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
async def graph_impact(
    uid: str,
    direction: str = Query("downstream"),
    depth: int = Query(3),
    confidence_min: float = Query(0.5),
    _rl=Depends(make_rate_limit_dep("graph.impact")),
    _m=Depends(make_metrics_dep("graph.impact")),
):
    """Blast-radius grouped by risk tier.

    PURPOSE: HTTP wrapper for cos_graph_impact.
    INPUT:   uid (path), direction, depth, confidence_min.
    OUTPUT:  {data: {root, tiers, impacted_count}, meta} on 200.
    DEPENDENCIES: graph_os.tools.graph.cos_graph_impact.
    NOTES:   direction is "downstream" | "upstream" | "both".
    """
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    result = g.cos_graph_impact(uid, direction=direction, depth=depth, confidence_min=confidence_min)
    return unwrap(result)


@router.get("/detect-changes")
async def graph_detect_changes(
    files: Optional[str] = Query(None, description="Comma-separated file paths"),
    scope: str = Query("working"),
    analyze_downstream: bool = Query(True),
    _rl=Depends(make_rate_limit_dep("graph.detect_changes")),
    _m=Depends(make_metrics_dep("graph.detect_changes")),
):
    """Map changed files to affected symbols.

    PURPOSE: HTTP wrapper for cos_graph_detect_changes.
    INPUT:   files (csv), scope, analyze_downstream.
    OUTPUT:  {data: {files, symbols, downstream_tasks, risk_level}, meta} on 200.
    DEPENDENCIES: graph_os.tools.graph.cos_graph_detect_changes.
    NOTES:   files is a comma-separated string.
    """
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    files_list = [f.strip() for f in files.split(",") if f.strip()] if files else None
    result = g.cos_graph_detect_changes(scope=scope, files=files_list, analyze_downstream=analyze_downstream)
    return unwrap(result)


@router.get("/trace/{entry_uid:path}")
async def graph_trace(
    entry_uid: str,
    terminals: str = Query("return,exception"),
    max_steps: int = Query(50),
    _rl=Depends(make_rate_limit_dep("graph.trace")),
    _m=Depends(make_metrics_dep("graph.trace")),
):
    """Forward execution walk from an entry point.

    PURPOSE: HTTP wrapper for cos_graph_trace.
    INPUT:   entry_uid (path), terminals (csv), max_steps.
    OUTPUT:  {data: {entry, steps, branches, terminals}, meta} on 200.
    DEPENDENCIES: graph_os.tools.graph.cos_graph_trace.
    NOTES:   terminals is a comma-separated string.
    """
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    terms = tuple(t.strip() for t in terminals.split(",") if t.strip()) or ("return", "exception")
    result = g.cos_graph_trace(entry_uid, terminals=terms, max_steps=max_steps)
    return unwrap(result)


@router.get("/similar/{uid:path}")
async def graph_similar(
    uid: str,
    top_k: int = Query(5),
    confidence_min: float = Query(0.5),
    _rl=Depends(make_rate_limit_dep("graph.similar")),
    _m=Depends(make_metrics_dep("graph.similar")),
):
    """Top-K nodes most similar to uid.

    PURPOSE: HTTP wrapper for cos_graph_similar.
    INPUT:   uid (path), top_k, confidence_min.
    OUTPUT:  {data: {root, results}, meta} on 200.
    DEPENDENCIES: graph_os.tools.graph.cos_graph_similar.
    NOTES:   Uses difflib baseline; BGE-M3 lands in S-future.
    """
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    result = g.cos_graph_similar(uid, top_k=top_k, confidence_min=confidence_min)
    return unwrap(result)


@router.get("/references/{uid:path}")
async def graph_references(
    uid: str,
    kinds: str = Query("calls,accesses_field,imports,references_doc"),
    limit: int = Query(100),
    _rl=Depends(make_rate_limit_dep("graph.references")),
    _m=Depends(make_metrics_dep("graph.references")),
):
    """Inbound references to uid.

    PURPOSE: HTTP wrapper for cos_graph_references.
    INPUT:   uid (path), kinds (csv), limit.
    OUTPUT:  {data: {node, references, count}, meta} on 200.
    DEPENDENCIES: graph_os.tools.graph.cos_graph_references.
    NOTES:   kinds is a comma-separated string.
    """
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    kinds_tuple = tuple(k.strip() for k in kinds.split(",") if k.strip())
    result = g.cos_graph_references(uid, kinds=kinds_tuple, limit=limit)
    return unwrap(result)


@router.get("/path")
async def graph_path(
    source_uid: str = Query(...),
    target_uid: str = Query(...),
    max_hops: int = Query(5),
    _rl=Depends(make_rate_limit_dep("graph.path")),
    _m=Depends(make_metrics_dep("graph.path")),
):
    """Shortest path between two nodes.

    PURPOSE: HTTP wrapper for cos_graph_path.
    INPUT:   source_uid, target_uid, max_hops (all query params).
    OUTPUT:  {data: {path, edges, hops, truncated}, meta} on 200.
    DEPENDENCIES: graph_os.tools.graph.cos_graph_path.
    NOTES:   Uses BFS with 1000-edge hop limit.
    """
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    result = g.cos_graph_path(source_uid, target_uid, max_hops=max_hops)
    return unwrap(result)


@router.get("/export")
async def graph_export(
    format: str = Query("json"),
    root_uid: Optional[str] = Query(None),
    edge_types: Optional[str] = Query(None),
    max_nodes: int = Query(500),
    include_spine: bool = Query(False),
    _rl=Depends(make_rate_limit_dep("graph.export")),
    _m=Depends(make_metrics_dep("graph.export")),
):
    """Export a subgraph as json | mermaid | dot.

    PURPOSE: HTTP wrapper for cos_graph_export.
    INPUT:   format, root_uid, edge_types (csv), max_nodes, include_spine.
    OUTPUT:  {data: {format, nodes|diagram, edges}, meta} on 200.
    DEPENDENCIES: graph_os.tools.graph.cos_graph_export.
    NOTES:   Large exports may be slow; use max_nodes to cap.
    """
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    et = [e.strip() for e in edge_types.split(",") if e.strip()] if edge_types else None
    result = g.cos_graph_export(
        format=format,
        root_uid=root_uid,
        edge_types=et,
        max_nodes=max_nodes,
        include_spine=include_spine,
    )
    return unwrap(result)


@router.get("/rename-plan/{uid:path}")
async def graph_rename_plan(
    uid: str,
    new_name: str = Query(...),
    check_strings: bool = Query(True),
    _rl=Depends(make_rate_limit_dep("graph.rename_plan")),
    _m=Depends(make_metrics_dep("graph.rename_plan")),
):
    """Plan a rename — call-sites, docs, tests, risk.

    PURPOSE: HTTP wrapper for cos_graph_rename_plan.
    INPUT:   uid (path), new_name, check_strings.
    OUTPUT:  {data: {old_name, new_name, call_sites, ...}, meta} on 200.
    DEPENDENCIES: graph_os.tools.graph.cos_graph_rename_plan.
    NOTES:   Read-only — doesn't actually perform the rename.
    """
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    result = g.cos_graph_rename_plan(uid, new_name, check_strings=check_strings)
    return unwrap(result)


@router.get("/contracts")
async def graph_contracts(
    scope: str = Query("all"),
    kinds: str = Query("http,mcp,grpc,event,websocket"),
    _rl=Depends(make_rate_limit_dep("graph.contracts")),
    _m=Depends(make_metrics_dep("graph.contracts")),
):
    """Enumerate every handler declared in the graph.

    PURPOSE: HTTP wrapper for cos_graph_contracts.
    INPUT:   scope, kinds (csv).
    OUTPUT:  {data: {http_routes, mcp_tools, ...}, meta} on 200.
    DEPENDENCIES: graph_os.tools.graph.cos_graph_contracts.
    NOTES:   Useful for contract tests and API surface audits.
    """
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    kinds_tuple = tuple(k.strip() for k in kinds.split(",") if k.strip())
    result = g.cos_graph_contracts(scope=scope, kinds=kinds_tuple)
    return unwrap(result)


@router.get("/communities")
async def graph_communities(
    top: int = Query(50, ge=1, le=200),
    min_size: int = Query(2, ge=1, le=100),
    _rl=Depends(make_rate_limit_dep("graph.communities")),
    _m=Depends(make_metrics_dep("graph.communities")),
):
    """Louvain-detected processes for the Hub Search tab grouping (TASK-075).

    PURPOSE: HTTP wrapper for cos_graph_communities.
    INPUT:   top (1-200), min_size (1-100).
    OUTPUT:  {data: {processes: [...]}, meta}.
    """
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    return unwrap(g.cos_graph_communities(top=int(top), min_size=int(min_size)))


@router.get("/entrypoints")
async def graph_entrypoints(
    top: int = Query(20, ge=1, le=200),
    kind: str = Query(""),
    min_score: float = Query(0.05, ge=0.0, le=1.0),
    _rl=Depends(make_rate_limit_dep("graph.entrypoints")),
    _m=Depends(make_metrics_dep("graph.entrypoints")),
):
    """Scored entry points for the Hub Graph tab (TASK-081).

    PURPOSE: HTTP wrapper for cos_graph_entrypoints.
    INPUT:   top (1-200), kind (main|cli|http|cron|test), min_score.
    OUTPUT:  {data: {entrypoints: [...]}, meta}.
    DEPENDENCIES: graph_os.tools.graph.cos_graph_entrypoints.
    """
    g = _tools()
    if g is None:
        return unwrap(_unavailable())
    result = g.cos_graph_entrypoints(
        top=int(top),
        kind=(kind or None),
        min_score=float(min_score),
    )
    return unwrap(result)
