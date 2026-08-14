"""Export tools: export + blend/process views + mermaid/dot serializers.

Private module of graph_os.tools.graph — import via the graph module,
never directly (the kernel imports this file at its bottom).
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Sequence
from typing import Any

from ..backend import BackendUnavailable, GraphBackend
from ..types import GraphEdge, GraphNode
from . import graph as _kernel
from ._graph_export_processes import _export_processes as _export_processes
from .graph import (
    NodeSummary,
    _bulk_nodes,
    _contains_ancestors,
    _degree_map_for,
    _edge_to_dict,
    _fail,
    _normalize_kinds,
    _ok,
    _walk_bfs,
)

_CONTAINS_EDGES: tuple[str, ...] = ("contains",)

# Noise nodes that pollute the graph viewer when shown.  They're real
# graph data (extracted by md_links / frontmatter parsers) but they're
# not navigation targets — they belong in the docs RAG, not the canvas.
_DEFAULT_NOISE_KINDS: frozenset[str] = frozenset(
    {
        # Pure metadata that's already shown in the docs RAG / contains tree —
        # surfacing it on the graph canvas just creates visual noise.
        "doc:frontmatter_key",
        "doc_frontmatter",
        "doc:heading",
        "doc_heading",
        # Unresolved external identifiers (typing.*, builtins, dynamic
        # method accesses) — they're stub nodes synthesised to satisfy
        # FK constraints, not navigation targets. Hidden by default; pass
        # `exclude_kinds=""` to show them when you really need to.
        "identifier",
    }
)

# Diversified blend recipe for the auto mode. Pulling the
# first N edges by confidence happens to over-represent whichever edge
# type the SQL ORDER BY surfaces first (in the live graph: handles_tool
# at 200+ rows).  Allocating per-bucket quotas guarantees every kind of
# semantic relationship lands in the result.
_AUTO_BLEND_BUCKETS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("calls", ("calls", "constructs")),
    ("imports", ("imports", "imports_type", "re_exports")),
    ("inherit", ("inherits_from", "implements", "extends")),
    ("handle", ("handles_route", "handles_tool", "handles_event", "dispatches", "defines_route")),
    ("type", ("has_param_type", "returns_type", "field_of_type", "accesses_field")),
    # Doc cross-references — `links_to` alone carries 1.5K+ edges; the
    # previous blend had no bucket so auto-mode renderings of the doc
    # subgraph showed nothing but contains spine.
    ("doc_link", ("links_to", "cites_heading", "references_doc", "read_next", "references")),
    # Decorators + module-level declarations.
    ("decoration", ("is_decorated_by", "declares")),
    ("contains", ("contains",)),
)

# W7 / R4-05 fix: the canonical set of edge types the graph CAN
# contain — the validation oracle for `edge_types` filters. A SUPERSET of every
# type any extractor emits, PLUS the query-only/view types the tool layer
# filters on (accesses_field / defines_route / tested_by are referenced by the
# blend buckets + test-gap queries but never emitted as rows). Being a superset
# is deliberate: an over-accepted filter just returns [] (harmless), whereas a
# MISSING real type would reject a legitimate filter on a POPULATED graph.
# Validate against THIS — never against `SELECT DISTINCT edge_type`, which is
# empty on a fresh / sparse / mid-build graph and made valid filters like
# 'contains' look like typos (the graph-os contract is "empty result is valid").
# Drift guard: src/core/graph_os/tests/test_graph_empty_state.py.
_KNOWN_EDGE_TYPES: frozenset[str] = frozenset(
    {
        # Code structure + calls
        "calls",
        "calls_contract",
        "calls_mcp_tool",
        "constructs",
        "dispatches",
        "awaits",
        "imports",
        "imports_type",
        "re_exports",
        "inherits_from",
        "implements",
        "extends",
        "is_decorated_by",
        "declares",
        # Types
        "has_param_type",
        "has_return_type",
        "returns_type",
        "field_of_type",
        "accesses_field",
        # Contracts / surfaces
        "handles_route",
        "handles_event",
        "handles_tool",
        "handles_command",
        "handles_test",
        "defines_route",
        # Docs
        "links_to",
        "cites_heading",
        "references_doc",
        "read_next",
        "references",
        # Spine / community / task / test
        "contains",
        "member_of_community",
        "produces_code",
        "depends_on",
        "blocks",
        "tested_by",
    }
)


def cos_graph_export(
    *,
    format: str = "json",
    root_uid: str | None = None,
    edge_types: Sequence[str] | None = None,
    max_nodes: int = 500,
    max_hops: int | None = None,
    include_spine: bool = False,
    mode: str = "auto",
    exclude_kinds: Sequence[str] | None = None,
    scope: str = "neighborhood",
    backend: str | None = None,
) -> dict[str, Any]:
    """Export a subgraph in `json | mermaid | dot`.

    TASK-141: ``mode`` selects the view-mode blend used when no root is
    pinned.  Hub Graph tab consumes this directly:

      - ``auto`` (default): blend of semantic (~60%) + contains (~40%).
        The previous behaviour returned 100% contains because the SQL
        order-by confidence happens to put `contains` (1.0) first —
        that's the fix the hub UI hairball needed.
      - ``containment``: contains-only (folder → file → class → method).
      - ``dependencies``: semantic-only (calls / imports / handles_* /
        inherits_from / implements / dispatches / awaits / ...).
      - ``processes``: returns Louvain community nodes + their members.

    ``exclude_kinds`` filters noise nodes (frontmatter keys, doc
    headings).  Defaults to a built-in set when None — pass an empty
    list to disable.
    """
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    if format not in {"json", "mermaid", "dot"}:
        return _fail("validation", f"unknown format {format!r}")
    if mode not in {"auto", "containment", "dependencies", "processes"}:
        return _fail(
            "validation",
            f"mode must be one of auto/containment/dependencies/processes (got {mode!r})",
        )
    if scope not in {"neighborhood", "subtree"}:
        return _fail("validation", f"scope must be neighborhood|subtree (got {scope!r})")

    # G3: normalize edge_types + exclude_kinds (wire trap)
    parsed_edge_types = _normalize_kinds(edge_types) or None
    # W7 / R4-05: reject a typo'd edge_type, but validate against
    # the canonical schema set (_KNOWN_EDGE_TYPES) — NOT the edge_types PRESENT
    # in the DB. A fresh / sparse / mid-build graph has few or zero distinct
    # edge_types, and the old SELECT-DISTINCT oracle rejected legitimate types
    # like 'contains' as "unknown". A valid filter on an empty graph must return
    # ok([]) (the graph-os "empty result is valid" contract); only a genuine
    # typo is a fail. No DB read here, so it also runs on non-SQLite backends.
    if parsed_edge_types:
        unknown = [e for e in parsed_edge_types if e not in _KNOWN_EDGE_TYPES]
        if unknown:
            return _fail(
                "validation",
                f"unknown edge_type(s) {unknown}; known: {sorted(_KNOWN_EDGE_TYPES)}",
            )
    # exclude_kinds None → default noise list; [] explicit → no filter.
    if exclude_kinds is None:
        excluded = _DEFAULT_NOISE_KINDS
    else:
        parsed_exclude_kinds = _normalize_kinds(exclude_kinds)
        excluded = frozenset(parsed_exclude_kinds)
    # G35: hard global ceiling on max_nodes. Raised 2000 → 50000
    #: the Hub sends 10k (rooted depth=all) / 30k (spine
    # sidebar) and the old silent clamp cut both to 2000 — the user-
    # visible "max still shows an incomplete graph". Sigma renders ~40k
    # nodes (enterprise viz audit) and the 5 MB coherent-subgraph
    # trimmer in ok() remains the OOM safety net above this.
    max_nodes_requested = int(max_nodes)
    max_nodes = max(1, min(max_nodes_requested, 50_000))

    # over-fetch when a noise filter applies so the budget is
    # spent on VISIBLE nodes — the old fetch-then-filter order burned the
    # budget on doc_heading/frontmatter rows that the filter dropped a few
    # lines later (the spine sidebar got 306 of 400 folders at a 30k ask).
    # only the BLEND path needs the over-fetch — the rooted walk
    # filters noise kinds DURING the BFS, so its budget already counts
    # visible nodes and a 4× walk would just quadruple latency.
    fetch_budget = min(max_nodes * 4, 150_000) if excluded else max_nodes
    if root_uid is not None:
        # Hub Graph tab "depth=all" sent max_nodes=10000 but the walk
        # stopped at 3 hops, so subfolder contents never appeared
        # (user-reported: "max doesn't show 100%"). Accept the
        # frontend's depth choice and clamp to a safe ceiling.
        effective_hops = 3 if max_hops is None else max(1, min(int(max_hops), 16))
        if scope == "subtree":
            # a rooted view means THIS subtree. The old "both"
            # neighborhood walk climbed one hop to the parent and flooded
            # the whole repo (probe: 26 of 8008 nodes inside the chosen
            # folder). Walk `contains` downward only, then overlay the
            # semantic edges among the members.
            nodes, edges = _walk_bfs(
                be,
                root_uid=root_uid,
                direction="out",
                max_hops=effective_hops,
                confidence_min=0.0,
                edge_types=("contains",),
                visit_limit=max_nodes,
                exclude_kinds=excluded,
            )
            member_uids = [n.uid for n in nodes]
            edges_among_fn = getattr(be, "edges_among", None)
            if callable(edges_among_fn) and member_uids:
                edges = list(edges) + list(
                    edges_among_fn(member_uids, edge_types=parsed_edge_types)
                )
        else:
            nodes, edges = _walk_bfs(
                be,
                root_uid=root_uid,
                direction="both",
                max_hops=effective_hops,
                confidence_min=0.0,
                edge_types=parsed_edge_types,
                visit_limit=max_nodes,
                exclude_kinds=excluded,
            )
    elif mode == "processes":
        nodes, edges = _export_processes(be, max_nodes=max_nodes)
    else:
        nodes, edges = _export_blend(
            be,
            mode=mode,
            edge_types=parsed_edge_types,
            max_nodes=fetch_budget,
        )

    # apply noise filter BEFORE the budget cap. Drop nodes whose kind is
    # in ``excluded`` AND drop any edges that touch them.
    if excluded:
        nodes = [n for n in nodes if (n.kind or "") not in excluded]
        kept_uids = {n.uid for n in nodes}
        edges = [e for e in edges if e.source_uid in kept_uids and e.target_uid in kept_uids]

    # G35: hard-enforce node cap after blend + filter (per-bucket leak).
    # Walk/blend results are nearest-first, so trimming keeps the most
    # relevant frontier.
    if len(nodes) > max_nodes:
        nodes = nodes[:max_nodes]
        kept_uids = {n.uid for n in nodes}
        edges = [e for e in edges if e.source_uid in kept_uids and e.target_uid in kept_uids]

    # S3: when include_spine is set, extend the subgraph with the
    # CONTAINS-ancestor chain of the root (or the deepest file node
    # present when no root is specified) so the tree-view has a
    # connected Folder→...→leaf backbone.
    if include_spine:
        seed_uid = root_uid
        if seed_uid is None:
            for n in nodes:
                if (n.kind or "").startswith(("file", "code:file", "doc:file")):
                    seed_uid = n.uid
                    break
        if seed_uid:
            ancestors, spine_edges = _contains_ancestors(be, leaf_uid=seed_uid)
            existing_uids = {n.uid for n in nodes}
            for a in ancestors:
                if a.uid not in existing_uids:
                    nodes.append(a)
                    existing_uids.add(a.uid)
            edges = list(edges) + list(spine_edges)

    if format == "json":
        # Server-side degree map so consumers (3D adapter, search,
        # NodeInspector) all see the same hub score without each
        # recomputing client-side.
        degree_map = _degree_map_for(be, [n.uid for n in nodes])
        node_dicts = [
            NodeSummary.from_node(n, degree=degree_map.get(n.uid)).to_dict() for n in nodes
        ]
        edge_dicts = [_edge_to_dict(e) for e in edges]
        payload: dict[str, Any] = {
            "format": "json",
            "nodes": node_dicts,
            "edges": edge_dicts,
        }
    elif format == "mermaid":
        payload = {"format": "mermaid", "diagram": _to_mermaid(nodes, edges)}
    else:  # dot
        payload = {"format": "dot", "diagram": _to_dot(nodes, edges)}
    return _ok(
        payload,
        meta={
            "backend": be.backend_id,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "include_spine": include_spine,
            # honest budget provenance — the Hub badge reads
            # these instead of guessing from its own request params.
            "max_nodes_requested": max_nodes_requested,
            "max_nodes_effective": max_nodes,
            "max_hops_effective": (
                (3 if max_hops is None else max(1, min(int(max_hops), 16)))
                if root_uid is not None
                else None
            ),
            "result_truncated": len(nodes) >= max_nodes or max_nodes < max_nodes_requested,
        },
    )


def _export_blend(
    be: GraphBackend,
    *,
    mode: str,
    edge_types: Sequence[str] | None,
    max_nodes: int,
) -> tuple[list[GraphNode], list[GraphEdge]]:
    """Compose the node + edge list for ``auto`` / ``containment`` /
    ``dependencies`` modes (TASK-141).

    The SQL list_edges API orders by ``(confidence DESC, id ASC)`` so
    a flat call with edge_types=None puts every contains edge
    (confidence=1.0) ahead of every semantic edge.  This helper
    explicitly partitions the budget so semantic relationships always
    land in the result.
    """
    if edge_types is not None:
        edges = list(be.list_edges(edge_types=tuple(edge_types), limit=max_nodes))
    elif mode == "containment":
        edges = list(be.list_edges(edge_types=_CONTAINS_EDGES, limit=max_nodes))
    elif mode == "dependencies":
        # Diversified pull across all semantic buckets so the result
        # isn't dominated by a single kind (e.g. handles_tool when MCP
        # registrations are dense).  Skip the contains bucket here.
        per_bucket = max(1, max_nodes // (len(_AUTO_BLEND_BUCKETS) - 1))
        edges = []
        for _, types in _AUTO_BLEND_BUCKETS:
            if types == _CONTAINS_EDGES:
                continue
            edges.extend(be.list_edges(edge_types=types, limit=per_bucket))
        edges = edges[:max_nodes]
    else:  # mode == "auto"
        # Equal-share quota across every bucket, then trim to budget.
        # Guarantees every semantic kind shows up alongside contains.
        per_bucket = max(1, max_nodes // len(_AUTO_BLEND_BUCKETS))
        edges = []
        for _, types in _AUTO_BLEND_BUCKETS:
            edges.extend(be.list_edges(edge_types=types, limit=per_bucket))
        edges = edges[:max_nodes]

    node_uids: set[str] = set()
    for e in edges:
        node_uids.add(e.source_uid)
        node_uids.add(e.target_uid)
    # batched hydration — one get_node per uid was ~30k round
    # trips on a spine export.
    nodes = list(_bulk_nodes(be, list(node_uids)).values())

    # Spine connectivity: walk every node up the ancestor chain so the
    # SPA's tree builder sees a connected forest. Without this, budget-
    # driven exports drop intermediate folder→file edges and the
    # orphans surface as fake "extra roots" (user's screenshot bug).
    # Only kicks in when contains is genuinely in scope — `dependencies`
    # mode promises no contains edges, so we leave its result alone.
    contains_in_scope = (
        edge_types is not None and any(t == "contains" for t in edge_types)
    ) or mode in ("auto", "containment")
    if node_uids and contains_in_scope:
        existing_pairs = {(e.source_uid, e.target_uid, e.edge_type) for e in edges}
        nodes_by_uid = {n.uid: n for n in nodes}
        # set-wise closure (one query per tree level in the
        # backend) — the previous per-node `_contains_ancestors` loop was
        # ~30k upward walks and dominated the export latency.
        closure_fn = getattr(be, "contains_ancestors_bulk", None)
        if callable(closure_fn):
            ancestors, spine_edges = closure_fn(list(node_uids))
        else:  # non-SQLite backend — per-leaf fallback
            ancestors, spine_edges = [], []
            for uid in list(node_uids):
                leaf_nodes, leaf_edges = _contains_ancestors(be, leaf_uid=uid)
                ancestors.extend(leaf_nodes)
                spine_edges.extend(leaf_edges)
        for a in ancestors:
            if a.uid not in nodes_by_uid:
                nodes_by_uid[a.uid] = a
                node_uids.add(a.uid)
        for se in spine_edges:
            key = (se.source_uid, se.target_uid, se.edge_type)
            if key not in existing_pairs:
                edges.append(se)
                existing_pairs.add(key)
        nodes = list(nodes_by_uid.values())

    return nodes, edges


def _to_mermaid(nodes: Iterable[GraphNode], edges: Iterable[GraphEdge]) -> str:
    lines = ["graph LR"]
    for n in nodes:
        lines.append(f'  {_safe_id(n.uid)}["{_escape(n.label or n.uid)}"]')
    for e in edges:
        lines.append(f"  {_safe_id(e.source_uid)} -->|{e.edge_type}| {_safe_id(e.target_uid)}")
    return "\n".join(lines)


def _to_dot(nodes: Iterable[GraphNode], edges: Iterable[GraphEdge]) -> str:
    lines = ["digraph G {"]
    for n in nodes:
        lines.append(f'  "{_safe_id(n.uid)}" [label="{_escape(n.label or n.uid)}"]')
    for e in edges:
        lines.append(
            f'  "{_safe_id(e.source_uid)}" -> "{_safe_id(e.target_uid)}" [label="{e.edge_type}"]'
        )
    lines.append("}")
    return "\n".join(lines)


def _safe_id(uid: str) -> str:
    # F5 / Audit #14: previous impl `re.sub(..., "_", uid)[:60]` made
    # every method of one class collapse to identical mermaid/dot node
    # IDs (uid prefix is the same — class+method suffix got chopped).
    # Suffix an 8-char digest so IDs are collision-proof regardless of uid
    # length, and keep a readable 40-char prefix for diagram legibility.
    sanitised = re.sub(r"[^A-Za-z0-9_]", "_", uid)
    if len(sanitised) <= 48:
        return sanitised
    digest = hashlib.sha256(uid.encode("utf-8")).hexdigest()[:8]
    return f"{sanitised[:40]}_{digest}"


def _escape(text: str) -> str:
    # W7 / R4-23: conservative escape safe for BOTH dot + mermaid quoted
    # labels. Backslash first (else it double-escapes), then quotes →
    # single-quote (avoids the dot \" / mermaid #quot; divergence), then
    # collapse any newline / control char to a space so the one-line
    # `id["label"]` / `id [label="..."]` syntax never breaks.
    # SECURITY: deliberately NOT HTML-escaped — `<`, `>`, `&` pass
    # through verbatim because HTML-encoding here would corrupt .mmd/.dot/CLI
    # output. HTML-context escaping of a label belongs at the browser
    # DOM/render boundary, never in this syntax-only helper. No HTML sink
    # exists today (the SPA renders format=json via Sigma WebGL).
    out = text.replace("\\", "/").replace('"', "'")
    return "".join(" " if (c == "\n" or c == "\r" or ord(c) < 32) else c for c in out)
