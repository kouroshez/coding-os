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
        "imports_type",
        "re_exports",
        "references_doc",
    ),
    "interface": (
        "implements",
        "has_param_type",
        "returns_type",
        "field_of_type",
        "inherits_from",
        "extends",
        "imports",
        "imports_type",
        "re_exports",
    ),
    "function": (
        "calls",
        "awaits",
        "dispatches",
        "accesses_field",
        "imports",
        "imports_type",
        "re_exports",
        "is_decorated_by",
        "references_doc",
    ),
    "method": (
        "calls",
        "awaits",
        "dispatches",
        "accesses_field",
        "imports",
        "is_decorated_by",
        "references_doc",
    ),
    "variable": (
        "accesses_field",
        "has_param_type",
        "imports",
        "imports_type",
        "re_exports",
        "references_doc",
    ),
    # `import type` and barrel re-exports are importers too: without them react
    # counted 207 of the 344 files that import it.
    "module": (
        "imports",
        "imports_type",
        "re_exports",
        "calls",
        "references_doc",
    ),
    # A folder containing the file is not a dependent; its `contains` edge used
    # to make an unimported file answer "1 reference".
    "file": (
        "imports",
        "imports_type",
        "re_exports",
        "calls",
        "links_to",
        "references_doc",
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
    # Structural/config kinds. Every one of these fell through to the code
    # default and reported 0 inbound edges while holding some — 1,538 edges
    # across the eight, not one of them a `calls` or an `imports`.
    "rule": (
        "contains",
        "links_to",
        "references_doc",
    ),
    "skill": (
        "contains",
        "links_to",
        "references_doc",
    ),
    "task": (
        "contains",
        "depends_on",
        "blocks",
        "references_doc",
    ),
    "route": (
        "handles_route",
        "handles_event",
        "contains",
        "references_doc",
    ),
    "tool": (
        "contains",
        "declares",
        "references_doc",
    ),
    "event": (
        "declares",
        "handles_event",
        "references_doc",
    ),
    "dependency": (
        "declares",
        "references_doc",
    ),
    "contract": (
        "declares",
        "references_doc",
    ),
}

# Rows scanned when a kinds-filtered query comes back empty, only to name the
# edge types that DO point at the node.
_ZERO_PROBE_LIMIT = 200


def _inbound_edge_types(backend: Any, target_uid: str) -> list[str]:
    try:
        edges = backend.list_edges(target_uid=target_uid, limit=_ZERO_PROBE_LIMIT)
    except Exception:
        return []
    return sorted({edge.edge_type for edge in edges})


def _stand_in_targets(backend: Any, file_uid: str) -> list[str]:
    """The nodes other files depend on in place of this file: its modules and a Go package."""
    contained = backend.list_edges(source_uid=file_uid, edge_types=("contains",), limit=50)
    modules = [edge.target_uid for edge in contained if edge.target_uid.startswith("code:module:")]
    packages = [
        edge.source_uid
        for module in modules
        for edge in backend.list_edges(target_uid=module, edge_types=("contains",), limit=10)
        if edge.source_uid.startswith("code:package:")
    ]
    return modules + packages


# Rows a package roll-up may merge: deep imports of one library, not a namespace.
_SUBMODULE_LIMIT = 500


def _submodule_targets(backend: Any, node: Any) -> list[str]:
    # `react/jsx-runtime`, `fastapi.testclient` and `fiber/v3/middleware/cors` are
    # the same library to whoever asks how many files use it.
    conn = getattr(backend, "_conn", None)
    if conn is None or node.file_path:
        return []
    if node.uid.startswith("code:module:npm:") or node.uid.startswith("code:external:"):
        pattern = f"{node.uid}/%"
    elif node.uid.startswith("code:module:"):
        pattern = f"{node.uid}.%"
    else:
        return []
    # `…/cors:New` is a symbol of the sub-package, not another package.
    return [
        row[0]
        for row in conn.execute(
            "SELECT uid FROM graph_nodes WHERE uid LIKE ? AND uid NOT LIKE ? "
            "AND file_path IS NULL LIMIT ?",
            (pattern, f"{pattern}:%", _SUBMODULE_LIMIT),
        ).fetchall()
    ]


def _source_files(backend: Any, targets: list[str], edge_types: Sequence[str]) -> int | None:
    conn = getattr(backend, "_conn", None)
    if conn is None:
        return None
    target_marks = ",".join("?" * len(targets))
    type_marks = ",".join("?" * len(edge_types))
    row = conn.execute(
        "SELECT COUNT(DISTINCT s.file_path) FROM graph_edges_v12 e "
        "JOIN graph_nodes t ON t.id = e.target_id JOIN graph_nodes s ON s.id = e.source_id "
        f"WHERE t.uid IN ({target_marks}) AND e.edge_type IN ({type_marks})",
        (*targets, *edge_types),
    ).fetchone()
    return int(row[0]) if row else 0


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
    # Importers point at a file's module (TS, Python) or its package (Go), not
    # at the file node, so `references(code:file:…)` answered 0 for files
    # imported by hundreds. A file's dependents are the union.
    targets = [canonical_uid]
    if node.kind == "file" and defaults_were_picked:
        targets += _stand_in_targets(be, canonical_uid)
    elif node.kind in ("module", "identifier") and defaults_were_picked:
        targets += _submodule_targets(be, node)
    edges = []
    total = 0
    for target in targets:
        edges += be.list_edges(target_uid=target, edge_types=parsed_kinds, limit=limit)
        # True total — separate count query so the caller knows if `edges`
        # is a complete picture or a slice. Uses the same kinds filter
        # because the backend's list_edges does the same filtering.
        total += _count_edges_for(be, target_uid=target, edge_types=parsed_kinds)
    edges = edges[:limit]
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
    if len(targets) > 1:
        references_meta["merged_targets"] = targets[1:]
    # An empty result reads as "nothing points here", which is wrong whenever the
    # node's real edges simply fall outside the kinds filter. `result_truncated`
    # cannot express that — it is False on a complete query of the wrong edges.
    if total == 0:
        present = _inbound_edge_types(be, canonical_uid)
        if present:
            references_meta["zero_from_kind_filter"] = True
            references_meta["edge_types_present"] = present
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
            # How many files depend on it — the fan-in answer, which edge
            # counts overstate when one file imports a library twice.
            "source_files": _source_files(be, targets, parsed_kinds),
        },
        meta=references_meta,
    )
