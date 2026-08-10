"""MCP envelope — the coherent trim for graph-export-shaped responses.

A `{nodes, edges}` payload is not a list of rows: dropping its tail yields a
disconnected slice, and dropping `edges` first yields a canvas the Hub cannot
render. So this trim is deliberately outside the ladder in `_envelope_trim` —
`ok()` routes the shape here instead, keeping the top-K nodes by degree plus
only the edges between kept nodes, so what survives is always a renderable
subgraph rather than an arbitrary prefix.

It also answers to its own, much larger budget (`GRAPH_SUBGRAPH_BUDGET_CHARS`):
a browser fetching the CONTAINS spine is not token-limited the way an agent
context is.
"""

from __future__ import annotations

from typing import Any

try:  # package import
    from ._envelope_size import TOKEN_BUDGET_CHARS, _probe_size
except ImportError:  # flat import
    from _envelope_size import (  # type: ignore[no-redef,import-not-found]
        TOKEN_BUDGET_CHARS,
        _probe_size,
    )


def _trim_coherent_subgraph(
    body: dict[str, Any],
    meta: dict[str, Any],
    *,
    budget_chars: int = TOKEN_BUDGET_CHARS,
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    # Drop nodes proportionally (top-K by degree + edges between kept nodes),
    # not edges-first, so the subgraph stays connected — the Hub UI must get a
    # renderable tree, never 0 edges/0 nodes.
    nodes = body.get("nodes")
    edges = body.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return body, meta, _probe_size(body, meta) <= budget_chars
    if not nodes or not edges:
        return body, meta, _probe_size(body, meta) <= budget_chars

    # Degree map: edges that reference each uid.
    degree: dict[str, int] = {}
    for e in edges:
        if isinstance(e, dict):
            src = e.get("source_uid") or e.get("src_uid") or e.get("source")
            dst = e.get("target_uid") or e.get("dst_uid") or e.get("target")
            if src:
                degree[src] = degree.get(src, 0) + 1
            if dst:
                degree[dst] = degree.get(dst, 0) + 1

    def _uid_of(n: Any) -> str | None:
        return n.get("uid") if isinstance(n, dict) else None

    # Sort nodes once: highest degree first, stable order for ties.
    nodes_sorted = sorted(
        nodes,
        key=lambda n: (-degree.get(_uid_of(n) or "", 0), nodes.index(n)),
    )
    original_n = len(nodes_sorted)
    original_e = len(edges)

    def _probe(k_nodes: int) -> tuple[list[Any], list[Any], int]:
        kept_nodes = nodes_sorted[:k_nodes]
        kept_uids = {_uid_of(n) for n in kept_nodes if _uid_of(n)}
        kept_edges = [
            e
            for e in edges
            if isinstance(e, dict)
            and (
                (e.get("source_uid") or e.get("src_uid") or e.get("source")) in kept_uids
                and (e.get("target_uid") or e.get("dst_uid") or e.get("target")) in kept_uids
            )
        ]
        trial = {**body, "nodes": kept_nodes, "edges": kept_edges}
        return kept_nodes, kept_edges, _probe_size(trial, meta)

    lo, hi = 0, original_n
    best_k = 0
    while lo < hi:
        mid = (lo + hi + 1) // 2
        _, _, size = _probe(mid)
        if size <= budget_chars:
            best_k = mid
            lo = mid
        else:
            hi = mid - 1

    kept_nodes, kept_edges, _ = _probe(best_k)
    did_trim = best_k < original_n or len(kept_edges) < original_e
    if did_trim:
        meta["truncated_subgraph"] = True
        meta["truncated_nodes_from"] = original_n
        meta["truncated_nodes_to"] = best_k
        meta["truncated_edges_from"] = original_e
        meta["truncated_edges_to"] = len(kept_edges)
        body = {**body, "nodes": kept_nodes, "edges": kept_edges}
    return body, meta, did_trim
