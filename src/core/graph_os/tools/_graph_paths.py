"""Multi-hop walks: cos_graph_trace and cos_graph_path.

Private module of graph_os.tools.graph — import via the graph module,
never directly (the kernel imports this file at its bottom).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
from typing import Any

from ..backend import BackendUnavailable
from ..types import GraphEdge
from . import graph as _kernel
from ._graph_envelope import (
    _fail,
    _ok,
    _validate_positive_int,
    logger,
)
from ._graph_lookup import (
    _fail_uid_not_found,
    _resolve_uid,
)
from ._graph_walk import (
    NodeSummary,
    _edge_to_dict,
)

# W7.8 / R4-12: in-repo modules that act as stub-hubs because every
# Python file imports from them. Treat them like ``code:external:*``
# in path-BFS to prevent meaningless bridges.
_PATH_STUB_HUB_MODULES: frozenset[str] = frozenset(
    {
        "__future__",
        "__init__",
        "typing",
        "typing_extensions",
        "annotations",
        "builtins",
    }
)


def _is_stub_hub_uid(uid: str) -> bool:
    """True when uid is a stub-hub (external stub or in-repo module hub)."""
    if uid.startswith("code:external:"):
        return True
    if uid.startswith("code:module:"):
        module = uid.split(":", 2)[-1]
        last = module.rsplit(".", 1)[-1]
        return last in _PATH_STUB_HUB_MODULES or module in _PATH_STUB_HUB_MODULES
    return False


def cos_graph_trace(
    entry_uid: str,
    *,
    terminals: Sequence[str] = ("return", "exception"),
    max_steps: int = 50,
    include_external: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """Forward execution walk from an entry point.

    F9 / Audit #7: `include_external=False` (default) keeps unresolved
    builtins / stdlib stubs (`code:external:*`) out of `steps`. They
    are collected in `external_targets` instead so the walk surface
    stays project-internal but the call-site relationship is still
    visible.
    """
    # W7.1 / R4-07: max_steps=0 returned empty steps + walk_truncated=true
    # (never walked). Reject as validation error.
    err = _validate_positive_int(max_steps, "max_steps")
    if err:
        return err
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    root, tried_entry_uids, resolved_from = _resolve_uid(be, entry_uid)
    start_source = "explicit"
    if root is None:
        # fall back to the highest-scoring entry point whose
        # label / file matches the supplied identifier.  Lets agents
        # call cos_graph_trace("login") without first running a
        # separate query to resolve the uid. The entry_points module
        # is part of an in-flight TASK; tolerate its absence so the
        # tool still returns a useful not_found instead of crashing.
        try:
            from .. import entry_points as ep_mod  # type: ignore[attr-defined]

            ep = ep_mod.best_start_for_query(be, entry_uid)
            if ep is not None:
                root = be.get_node(ep.uid)
                start_source = "entry-point-heuristic"
        except ImportError as exc:
            logger.debug("entry_points fallback unavailable: %s", exc)
    if root is None:
        return _fail_uid_not_found(entry_uid, tried_entry_uids, label="entry_uid")

    steps: list[dict[str, Any]] = []
    branches: list[dict[str, Any]] = []
    external_targets: list[str] = []
    seen: set[str] = set()
    stack: list[str] = [root.uid]
    while stack and len(steps) < max_steps:
        uid = stack.pop()
        if uid in seen:
            continue
        seen.add(uid)
        if not include_external and uid.startswith("code:external:"):
            external_targets.append(uid)
            continue
        node = be.get_node(uid)
        if node is None:
            continue
        steps.append(NodeSummary.from_node(node).to_dict())
        # B3: follow a wider set of outgoing control-flow edges so traces
        # cover API routes, MCP tool dispatch, event handlers, and async
        # awaits — not just direct calls/constructs.
        edges = be.list_edges(
            source_uid=uid,
            edge_types=(
                "calls",
                "constructs",
                "handles_route",
                "handles_tool",
                "handles_event",
                "dispatches",
                "awaits",
            ),
            limit=20,
        )
        if len(edges) > 1:
            # G24: strip externals from fan_out — they already live in
            # `external_targets`, so duplicating them in branches inflates
            # the envelope without new information.
            fan_out_uids = [e.target_uid for e in edges]
            if not include_external:
                fan_out_uids = [u for u in fan_out_uids if not u.startswith("code:external:")]
            branches.append(
                {
                    "from": uid,
                    "fan_out": fan_out_uids,
                }
            )
        for edge in edges:
            if edge.target_uid not in seen:
                stack.append(edge.target_uid)
    # Walk stopped either because the stack drained (complete) or
    # because the step cap fired (incomplete — caller should re-run
    # with a higher max_steps or split the trace at a branch).
    walk_truncated = len(steps) >= max_steps and bool(stack)
    return _ok(
        {
            "entry": NodeSummary.from_node(root).to_dict(),
            "steps": steps,
            "branches": branches,
            "external_targets": external_targets,
            "terminals": list(terminals),
            "start_source": start_source,
        },
        meta={
            "backend": be.backend_id,
            "step_count": len(steps),
            "external_count": len(external_targets),
            "start_source": start_source,
            "max_steps": max_steps,
            "walk_truncated": walk_truncated,
            "resolved_from": resolved_from,
        },
    )


def cos_graph_path(
    source_uid: str,
    target_uid: str,
    *,
    max_hops: int = 5,
    allow_external_intermediates: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """Shortest path between two nodes (any direction).

    B4: each hop pulls up to 1000 edges from the backend (up from 200).
    When either side's edge list hits that cap the result is flagged
    ``meta.truncated=True`` so callers know the search may have missed a
    shorter path that lives beyond the first 1000 neighbours.

    W6.4 (T1): `code:external:*` stubs are excluded from intermediate
    hops by default because `unresolved:str` has thousands of in-edges
    and produces meaningless bridges between unrelated nodes. Pass
    ``allow_external_intermediates=True`` to opt back in.
    """
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    src_node, tried_src, src_resolved_from = _resolve_uid(be, source_uid)
    if src_node is None:
        return _fail_uid_not_found(source_uid, tried_src, label="source_uid")
    tgt_node, tried_tgt, tgt_resolved_from = _resolve_uid(be, target_uid)
    if tgt_node is None:
        return _fail_uid_not_found(target_uid, tried_tgt, label="target_uid")
    source_uid = src_node.uid
    target_uid = tgt_node.uid
    # G11/G23/P5: separate the two distinct truncation concepts:
    #   * `walk_truncated` — search ran out of budget BEFORE reaching target
    #     (the previous "truncated" semantics blurred this with fanout-cap).
    #   * `frontier_saturated` — per-node fanout hit the cap (search may
    #     still have succeeded, but a wider neighbour list could yield a
    #     shorter path). Was the original `walk_truncated` semantics —
    #     renamed to stop the false-positive panic on 3-hop paths.
    # P5: hop edge cap reduced 1000 → 200 to stay sub-100ms at 1M-node.
    _PATH_HOP_LIMIT = 200
    frontier_saturated = False
    # W6.4 (T2): parents stores (prev_uid, edge, traversal_direction).
    parents: dict[str, tuple[str, GraphEdge, str] | None] = {source_uid: None}
    queue: deque[tuple[str, int]] = deque([(source_uid, 0)])
    found = source_uid == target_uid
    while queue and not found:
        uid, depth = queue.popleft()
        if uid == target_uid:
            found = True
            break
        if depth >= max_hops:
            continue
        out_edges = be.list_edges(source_uid=uid, limit=_PATH_HOP_LIMIT)
        if len(out_edges) >= _PATH_HOP_LIMIT:
            frontier_saturated = True
        for edge in out_edges:
            nxt = edge.target_uid
            # W6.4 (T1) + W7.8 (R4-12): skip external stubs AND in-repo
            # stub-hub modules (__future__, typing, __init__, …) which
            # bridge unrelated nodes. Target uid always exempt.
            if not allow_external_intermediates and _is_stub_hub_uid(nxt) and nxt != target_uid:
                continue
            if nxt not in parents:
                parents[nxt] = (uid, edge, "forward")
                queue.append((nxt, depth + 1))
        in_edges = be.list_edges(target_uid=uid, limit=_PATH_HOP_LIMIT)
        if len(in_edges) >= _PATH_HOP_LIMIT:
            frontier_saturated = True
        for edge in in_edges:
            nxt = edge.source_uid
            if not allow_external_intermediates and _is_stub_hub_uid(nxt) and nxt != target_uid:
                continue
            if nxt not in parents:
                parents[nxt] = (uid, edge, "reverse")
                queue.append((nxt, depth + 1))
    walk_truncated = (target_uid not in parents) and frontier_saturated
    if target_uid not in parents:
        return _ok(
            {
                "path": None,
                "edges": [],
                "walk_truncated": walk_truncated,
                "frontier_saturated": frontier_saturated,
            },
            meta={
                "backend": be.backend_id,
                "reason": "unreachable" if not frontier_saturated else "exhausted_budget",
                "walk_truncated": walk_truncated,
                "frontier_saturated": frontier_saturated,
                "max_hops": max_hops,
                "frontier_edge_limit": _PATH_HOP_LIMIT,
                "source_resolved_from": src_resolved_from,
                "target_resolved_from": tgt_resolved_from,
            },
        )
    chain: list[tuple[GraphEdge, str]] = []
    cur = target_uid
    while parents.get(cur) is not None:
        prev, edge, traversal_dir = parents[cur]  # type: ignore[misc]
        chain.append((edge, traversal_dir))
        cur = prev
    chain.reverse()
    # G29: walk the chain step-by-step so we don't emit consecutive
    # duplicate nodes. The previous "[source] + [e.target if e.source==source
    # else e.source for e]" was anchored to the original source, which broke
    # past the first hop.
    path_nodes: list[str] = [source_uid]
    prev_uid = source_uid
    edge_dicts: list[dict[str, Any]] = []
    for e, traversal_dir in chain:
        nxt_uid = e.target_uid if e.source_uid == prev_uid else e.source_uid
        path_nodes.append(nxt_uid)
        prev_uid = nxt_uid
        # W6.4 (T2): tag each edge with how the BFS traversed it so callers
        # can tell semantic-direction edges from reverse-edge bridges.
        ed = _edge_to_dict(e)
        ed["traversal_direction"] = traversal_dir
        edge_dicts.append(ed)
    return _ok(
        {
            "path": path_nodes,
            "edges": edge_dicts,
            "hops": len(chain),
            "walk_truncated": False,
            "frontier_saturated": frontier_saturated,
        },
        meta={
            "backend": be.backend_id,
            "walk_truncated": False,
            "frontier_saturated": frontier_saturated,
            "max_hops": max_hops,
            "frontier_edge_limit": _PATH_HOP_LIMIT,
            "allow_external_intermediates": allow_external_intermediates,
            "source_resolved_from": src_resolved_from,
            "target_resolved_from": tgt_resolved_from,
        },
    )
