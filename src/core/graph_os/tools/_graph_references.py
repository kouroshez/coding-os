"""Inbound-edge lookup: cos_graph_references and its per-kind vocabulary.

Private module of graph_os.tools.graph — import via the graph module,
never directly (the kernel imports this file at its bottom).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ..backend import BackendUnavailable
from . import graph as _kernel
from ._graph_envelope import (
    _fail,
    _file_freshness,
    _ok,
)
from ._graph_lookup import (
    _fail_uid_not_found,
    _normalize_kinds,
    _resolve_uid,
)
from ._graph_walk import (
    NodeSummary,
    _count_edges_for,
    _edge_to_dict,
)

# R4-02: per-node-kind default edge types for cos_graph_references.
# A class is referenced by `constructs` (instantiation) — different
# vocabulary than how a function is referenced (`calls`). Pick the
# edge-types relevant to the node's kind so the default answer for
# "who references X?" is meaningful for every kind, not just functions.
_REFERENCE_KINDS_BY_NODE_KIND: dict[str, tuple[str, ...]] = {
    "class": (
        "constructs",
        "has_param_type",
        "returns_type",
        "field_of_type",
        "inherits_from",
        "is_decorated_by",
        "imports",
        "references_doc",
    ),
    "interface": (
        "implements",
        "has_param_type",
        "returns_type",
        "field_of_type",
        "inherits_from",
        "imports",
    ),
    "function": (
        "calls",
        "accesses_field",
        "imports",
        "is_decorated_by",
        "references_doc",
    ),
    "method": (
        "calls",
        "accesses_field",
        "imports",
        "is_decorated_by",
        "references_doc",
    ),
    "variable": (
        "accesses_field",
        "has_param_type",
        "references_doc",
    ),
    "module": (
        "imports",
        "calls",
        "references_doc",
    ),
    "file": (
        "imports",
        "links_to",
        "references_doc",
        "contains",
    ),
    "doc_file": (
        "links_to",
        "cites_heading",
        "references_doc",
        "read_next",
    ),
    "doc_heading": (
        "links_to",
        "cites_heading",
        "references_doc",
    ),
    "folder": (
        "contains",
        "links_to",
        "references_doc",
    ),
    "mcp_tool": (
        "calls",
        "dispatches",
        "references_doc",
    ),
    "hook": (
        "handles_tool",
        "handles_event",
        "declares",
        "references_doc",
    ),
}


def _default_reference_kinds_for(node_kind: str | None) -> tuple[str, ...]:
    """Pick default inbound edge-types based on node kind (R4-02)."""
    if not node_kind:
        return ("calls", "accesses_field", "imports", "references_doc")
    return _REFERENCE_KINDS_BY_NODE_KIND.get(
        node_kind,
        ("calls", "accesses_field", "imports", "references_doc"),
    )


def cos_graph_references(
    uid: str,
    *,
    kinds: Sequence[str] | str | None = None,
    limit: int = 100,
    backend: str | None = None,
) -> dict[str, Any]:
    """Inbound edges to `uid` — "who references this?".

    Coverage contract (so silent truncation can't bite the agent):
      - ``count`` is the rows in *this* response (≤ limit).
      - ``total_count`` is the TRUE inbound-edge count across the kinds
        filter. If ``count < total_count`` the response is incomplete —
        the agent must either widen ``limit`` or narrow ``kinds``.
      - ``meta.result_truncated`` mirrors the same condition for fast
        inspection. (Distinct from the envelope-level ``meta.truncated``
        which signals *token-budget* truncation; result_truncated signals
        the caller-budget hit.)
    """
    # G22: validate + clamp limit
    if limit is not None and limit <= 0:
        return _fail("validation", "limit must be > 0")
    _LIMIT_MAX = 10_000
    limit_clamped = False
    if limit and limit > _LIMIT_MAX:
        limit = _LIMIT_MAX
        limit_clamped = True
    # G2 + G3: normalize kinds (caller-supplied wins; per-kind default
    # below kicks in only when caller passes empty).
    parsed_kinds = _normalize_kinds(kinds)

    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    node, tried_uids, resolved_from = _resolve_uid(be, uid)
    if node is None:
        return _fail_uid_not_found(uid, tried_uids)

    # R4-02: per-kind default — class nodes are accessed via `constructs`
    # (test instantiations) which is NOT in the function-default. Pick a
    # sensible default per node.kind so callers don't get 0 callers on a
    # class that has 30+ test constructs.
    defaults_were_picked = False
    if not parsed_kinds:
        parsed_kinds = _default_reference_kinds_for(node.kind)
        defaults_were_picked = True

    canonical_uid = node.uid
    edges = be.list_edges(target_uid=canonical_uid, edge_types=parsed_kinds, limit=limit)

    # True total — separate count query so the caller knows if `edges`
    # is a complete picture or a slice. Uses the same kinds filter
    # because the backend's list_edges does the same filtering.
    total = _count_edges_for(be, target_uid=canonical_uid, edge_types=parsed_kinds)
    truncated = total > len(edges)

    references_meta: dict[str, Any] = {
        "backend": be.backend_id,
        "kinds": list(parsed_kinds),
        "limit": limit,
        "limit_clamped": limit_clamped,
        "result_truncated": truncated,
        "resolved_from": resolved_from,
        "default_kinds_picked": defaults_were_picked,
        "node_kind": node.kind,
    }
    fresh = _file_freshness(be, node.file_path)
    if fresh is not None:
        references_meta["stale"] = fresh["stale"]
        references_meta["freshness"] = fresh
    return _ok(
        {
            "node": NodeSummary.from_node(node).to_dict(),
            "references": [_edge_to_dict(e) for e in edges],
            "count": len(edges),
            "total_count": total,
        },
        meta=references_meta,
    )
