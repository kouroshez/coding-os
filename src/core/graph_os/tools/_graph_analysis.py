"""Change-analysis tools: impact, detect_changes, rename_plan, diff, contracts.

Private module of graph_os.tools.graph — import via the graph module,
never directly (the kernel imports this file at its bottom).
"""

from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ..backend import BackendUnavailable, GraphBackend
from ..types import GraphEdge, GraphNode
from . import graph as _kernel
from .graph import (
    _BEHAVIOURAL_EDGE_TYPES,
    NodeSummary,
    _count_edges_for,
    _edge_to_dict,
    _fail,
    _fail_uid_not_found,
    _file_freshness,
    _normalize_kinds,
    _ok,
    _resolve_uid,
    _validate_confidence,
    _validate_positive_int,
    _walk_bfs,
    _write_consult_marker,
    logger,
)


def _file_contained_symbols(backend: GraphBackend, file_uid: str, *, limit: int = 500) -> list[str]:
    # W6.3 (F6/B15/N1): when caller hands us a `code:file:*` uid the
    # interesting blast radius lives on the SYMBOLS the file contains
    # (class/function/method), not on the file node itself. Return the
    # contains-children that have behavioural inbound surface area —
    # so impact + detect_changes can roll the file-level answer up from
    # the contained symbols.
    try:
        edges = backend.list_edges(source_uid=file_uid, edge_types=("contains",), limit=limit)
    except (BackendUnavailable, sqlite3.Error):
        # Read-fallback only — caller already has a valid root node;
        # missing contained-symbol expansion degrades to file-only walk.
        # Narrowed from bare-except so KeyboardInterrupt/SystemExit propagate.
        return []
    out: list[str] = []
    for e in edges:
        tgt = e.target_uid
        # Only symbol uids carry behavioural inbound edges.
        if tgt.startswith(("code:class:", "code:function:", "code:method:")):
            out.append(tgt)
    return out


def cos_graph_impact(
    uid: str,
    *,
    direction: str = "downstream",
    depth: int = 3,
    confidence_min: float = 0.3,
    visit_limit: int = 500,
    backend: str | None = None,
) -> dict[str, Any]:
    """Blast-radius: which nodes depend on (or are depended on by) `uid`.

    Direction semantics (B12):
      "downstream" — nodes that DEPEND ON `uid` (inbound edges from
                     their perspective, i.e. direction="in" in BFS).
                     These are the nodes that WILL BREAK if `uid`
                     changes. Example: callers of a function.

      "upstream"   — nodes that `uid` DEPENDS ON (outbound edges from
                     `uid`'s perspective, i.e. direction="out" in BFS).
                     These are the nodes `uid` CALLS / IMPORTS. Changes
                     to upstream nodes may require `uid` to adapt.
                     Example: libraries or helpers that `uid` imports.

      "both"       — walks in both directions simultaneously.

    DEPRECATION NOTE: the string "downstream" / "upstream" naming
      matches the semantic intent (downstream = consumers, upstream =
      dependencies). The legacy mapping to BFS direction is preserved
      exactly. Do NOT pass raw BFS direction strings ("in"/"out") to
      this parameter — they are unsupported and will default to "in".
    """
    # W7.1 / R4-19/R4-20: confidence in [0,1] + depth>=1.
    err = _validate_confidence(confidence_min, "confidence_min")
    if err:
        return err
    err = _validate_positive_int(depth, "depth")
    if err:
        return err
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    root, tried_uids, resolved_from = _resolve_uid(be, uid)
    if root is None:
        return _fail_uid_not_found(uid, tried_uids)

    walk_direction = {"downstream": "in", "upstream": "out", "both": "both"}.get(direction, "in")
    visit_limit = max(1, min(int(visit_limit), 50_000))

    # W6.3 (N1): file uids have ~no behavioural inbound edges of their
    # own — the blast radius lives on contained symbols. Walk each child
    # and merge the dedup'd union so callers asking about a file get a
    # meaningful answer instead of will_break=[].
    walk_roots = [root.uid]
    expanded_from_file = False
    if root.kind == "file":
        children = _file_contained_symbols(be, root.uid, limit=visit_limit)
        if children:
            # Children carry the behavioural surface area; the file uid
            # itself has only contains-edges (already walked as parents
            # of each child) and would consume visit_limit budget for
            # zero new signal. Drop it.
            walk_roots = children
            expanded_from_file = True

    seen_node_uids: set[str] = set()
    edges: list[GraphEdge] = []
    nodes: list[GraphNode] = []
    seen_edge_keys: set[tuple] = set()
    for sub_root in walk_roots:
        if len(seen_node_uids) >= visit_limit:
            break
        sub_nodes, sub_edges = _walk_bfs(
            be,
            root_uid=sub_root,
            direction=walk_direction,
            max_hops=max(1, int(depth)),
            confidence_min=confidence_min,
            edge_types=None,
            visit_limit=max(1, visit_limit - len(seen_node_uids)),
        )
        for n in sub_nodes:
            if n.uid in seen_node_uids:
                continue
            seen_node_uids.add(n.uid)
            nodes.append(n)
        for e in sub_edges:
            key = (e.source_uid, e.target_uid, e.edge_type)
            if key in seen_edge_keys:
                continue
            seen_edge_keys.add(key)
            edges.append(e)
    truncated = len(seen_node_uids) >= visit_limit
    tiers: dict[str, list[dict[str, Any]]] = {
        "will_break": [],
        "should_review": [],
        "context": [],
    }
    # F4 / Audit #5: tier classification is edge-type-aware, not pure
    # confidence. `contains` (file→class) has confidence=1.0 but is
    # structural — it never "breaks" when the target changes. Only
    # behavioural edges (calls / imports / constructs / type-usage /
    # dispatch / handler-binding) belong in `will_break`. Single SSOT
    # in `_BEHAVIOURAL_EDGE_TYPES` (module-level) so rename_plan +
    # impact stay in lockstep.
    for edge in edges:
        if edge.edge_type in _BEHAVIOURAL_EDGE_TYPES:
            if edge.confidence >= 0.7:
                bucket = "will_break"
            elif edge.confidence >= 0.4:
                bucket = "should_review"
            else:
                bucket = "context"
        else:
            # Structural / metadata edge (contains, tested_by, …) —
            # never a break risk; surface as context so the consumer
            # still sees the relationship.
            bucket = "context"
        tiers[bucket].append(_edge_to_dict(edge))

    impact_meta: dict[str, Any] = {
        "backend": be.backend_id,
        "depth": depth,
        "confidence_min": confidence_min,
        "visit_limit": visit_limit,
        "walk_truncated": truncated,
        "semantic_scope": "transitive_depth_" + str(depth),
        "expanded_from_file": expanded_from_file,
        "resolved_from": resolved_from,
    }
    fresh = _file_freshness(be, root.file_path)
    if fresh is not None:
        impact_meta["stale"] = fresh["stale"]
        impact_meta["freshness"] = fresh
    return _ok(
        {
            "root": NodeSummary.from_node(root).to_dict(),
            "direction": direction,
            "tiers": tiers,
            "impacted_count": max(0, len(nodes) - 1),
        },
        meta=impact_meta,
    )


def cos_graph_detect_changes(
    *,
    scope: str = "working",
    files: Sequence[str] | None = None,
    analyze_downstream: bool = True,
    backend: str | None = None,
) -> dict[str, Any]:
    """Pre-commit self-review: map changed files to affected graph nodes."""
    # G3: normalize files (FastMCP wire trap)
    parsed_files = _normalize_kinds(files)
    if not parsed_files:
        return _ok(
            {
                "scope": scope,
                "files": [],
                "symbols": [],
                "downstream_tasks": [],
                "risk_level": "none",
            },
            meta={"reason": "no files provided"},
        )
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    affected_symbols: list[dict[str, Any]] = []
    downstream_tasks: set[str] = set()
    downstream_consumers: list[dict[str, Any]] = []
    risk = "low"
    _DC_VISIT_LIMIT = 500
    walk_truncated = False

    for file_path in parsed_files:
        file_uid = f"code:file:{file_path}"
        node = be.get_node(file_uid)
        if node is None:
            continue
        nodes_1, edges = _walk_bfs(
            be,
            root_uid=file_uid,
            direction="both",
            max_hops=1,
            confidence_min=0.0,
            edge_types=None,
            visit_limit=_DC_VISIT_LIMIT,
        )
        if len(nodes_1) >= _DC_VISIT_LIMIT:
            walk_truncated = True
        for edge in edges:
            affected_symbols.append(
                {
                    "file": file_path,
                    "source": edge.source_uid,
                    "target": edge.target_uid,
                    "edge_type": edge.edge_type,
                }
            )
            # B15: collect task uids from both the 1-hop walk and, below,
            # the deep walk (depth 3, confidence >= 0.6).
            for uid_candidate in (edge.source_uid, edge.target_uid):
                if uid_candidate.startswith("task:file:"):
                    downstream_tasks.add(uid_candidate)
        if analyze_downstream:
            # W6.3 (F6/B15): walk from each contained SYMBOL (class/function/
            # method) instead of the file uid alone. File-level walk only
            # surfaces folder-contains parents — useless for risk. Roll the
            # behavioural inbound counts UP to file-level risk.
            walk_seeds = _file_contained_symbols(be, file_uid, limit=_DC_VISIT_LIMIT)
            if not walk_seeds:
                walk_seeds = [file_uid]
            seen_uids: set[str] = set()
            deep_edges: list[GraphEdge] = []
            seen_edges: set[tuple] = set()
            for seed in walk_seeds:
                if len(seen_uids) >= _DC_VISIT_LIMIT:
                    walk_truncated = True
                    break
                nodes_deep, sub_edges = _walk_bfs(
                    be,
                    root_uid=seed,
                    direction="in",
                    max_hops=3,
                    confidence_min=0.6,
                    edge_types=None,
                    visit_limit=max(1, _DC_VISIT_LIMIT - len(seen_uids)),
                )
                for n in nodes_deep:
                    seen_uids.add(n.uid)
                for e in sub_edges:
                    k = (e.source_uid, e.target_uid, e.edge_type)
                    if k in seen_edges:
                        continue
                    seen_edges.add(k)
                    deep_edges.append(e)
            if len(seen_uids) >= _DC_VISIT_LIMIT:
                walk_truncated = True
            # B15: also collect task uids from the deep (depth-3) walk.
            for deep_edge in deep_edges:
                for uid_candidate in (deep_edge.source_uid, deep_edge.target_uid):
                    if uid_candidate.startswith("task:file:"):
                        downstream_tasks.add(uid_candidate)
            # G19: risk reflects BLAST RADIUS (callers / behavioural
            # consumers), not contains-children inside the file. A new
            # file with 30 functions but zero callers is "low", not "high".
            behavioural = [e for e in deep_edges if e.edge_type in _BEHAVIOURAL_EDGE_TYPES]
            # F4: expose the computed blast radius (inbound behavioural
            # consumers). Previously this drove `risk` then was discarded,
            # so callers saw only contains-children — never the real callers
            # the walk already found.
            for e in behavioural:
                downstream_consumers.append(
                    {
                        "file": file_path,
                        "consumer": e.source_uid,
                        "target": e.target_uid,
                        "edge_type": e.edge_type,
                        "confidence": e.confidence,
                    }
                )
            if len(behavioural) > 20:
                risk = "high"
            elif len(behavioural) > 5 and risk != "high":
                risk = "medium"

    return _ok(
        {
            "scope": scope,
            "files": list(files),
            "symbols": affected_symbols,
            "downstream_consumers": downstream_consumers,
            "downstream_tasks": sorted(downstream_tasks),
            "risk_level": risk,
        },
        meta={
            "backend": be.backend_id,
            "analyze_downstream": analyze_downstream,
            "downstream_consumer_count": len(downstream_consumers),
            "visit_limit": _DC_VISIT_LIMIT,
            "walk_truncated": walk_truncated,
        },
    )


def cos_graph_rename_plan(
    uid: str,
    new_name: str,
    *,
    check_strings: bool = True,
    backend: str | None = None,
) -> dict[str, Any]:
    """Produce a rename plan — call-sites, docs, tests, strings."""
    if not new_name or not new_name.strip():
        return _fail("validation", "new_name must be non-empty")
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)
    root, tried_uids, resolved_from = _resolve_uid(be, uid)
    if root is None:
        return _fail_uid_not_found(uid, tried_uids)
    # R4-18: reject no-op rename (new_name equals current label)
    if new_name.strip() == (root.label or ""):
        return _fail(
            "validation",
            f"new_name {new_name!r} equals current label — no-op rename",
        )
    uid = root.uid

    # Rename plans MUST be exhaustive — a missed call-site leaves
    # broken code after rename. Counter each bucket separately so the
    # caller can see if the in-line slice was incomplete. Bucket pulls
    # from the same SSOT (`_BEHAVIOURAL_EDGE_TYPES`) impact uses,
    # minus `references_doc` which is counted under doc_edge_types
    # below to avoid double-counting.
    _RENAME_BUCKET_LIMIT = 500
    call_edge_types = tuple(sorted(_BEHAVIOURAL_EDGE_TYPES - {"references_doc"}))
    doc_edge_types = ("links_to", "cites_heading", "references_doc")
    test_edge_types = ("tested_by",)
    call_sites = [
        _edge_to_dict(e)
        for e in be.list_edges(
            target_uid=uid, edge_types=call_edge_types, limit=_RENAME_BUCKET_LIMIT
        )
    ]
    doc_refs = [
        _edge_to_dict(e)
        for e in be.list_edges(
            target_uid=uid, edge_types=doc_edge_types, limit=_RENAME_BUCKET_LIMIT
        )
    ]
    test_refs = [
        _edge_to_dict(e)
        for e in be.list_edges(
            target_uid=uid, edge_types=test_edge_types, limit=_RENAME_BUCKET_LIMIT
        )
    ]
    call_total = _count_edges_for(be, target_uid=uid, edge_types=call_edge_types)
    doc_total = _count_edges_for(be, target_uid=uid, edge_types=doc_edge_types)
    test_total = _count_edges_for(be, target_uid=uid, edge_types=test_edge_types)
    result_truncated = (
        call_total > len(call_sites) or doc_total > len(doc_refs) or test_total > len(test_refs)
    )
    risk = "high" if len(call_sites) > 20 else "medium" if call_sites else "low"

    if root.label:
        _write_consult_marker(
            f"plan-{root.label}",
            {
                "identifier": root.label,
                "uid": root.uid,
                "new_name": new_name,
                "tool": "cos_graph_rename_plan",
            },
        )
    return _ok(
        {
            "old_name": root.label,
            "new_name": new_name,
            "uid": root.uid,
            "call_sites": call_sites,
            "call_sites_total_count": call_total,
            "doc_references": doc_refs,
            "doc_references_total_count": doc_total,
            "test_references": test_refs,
            "test_references_total_count": test_total,
            "string_literals": [] if not check_strings else _grep_string_literals(root.label or ""),
            "risk": risk,
            "suggested_order": [
                "tests first",
                "implementation",
                "docs",
                "string literals last",
            ],
            "confidence": 0.9 if call_sites else 0.6,
        },
        meta={
            "backend": be.backend_id,
            "bucket_limit": _RENAME_BUCKET_LIMIT,
            "result_truncated": result_truncated,
            "resolved_from": resolved_from,
        },
    )


def _is_test_source(uid: str) -> bool:
    """True when a uid lives under a tests/ tree (R4-10)."""
    return "/tests/" in uid or ":tests/" in uid or "test_" in uid.rsplit("/", 1)[-1]


def cos_graph_contracts(
    *,
    scope: str = "all",
    kinds: Sequence[str] = ("http", "mcp", "grpc", "event", "websocket"),
    include_test_sources: bool = False,
    backend: str | None = None,
) -> dict[str, Any]:
    """API surface — enumerate every route / tool / event handler."""
    try:
        be = _kernel._backend(backend=backend)
    except BackendUnavailable as exc:
        return _fail("unavailable", str(exc), retryable=True)

    # G3: normalize kinds (wire trap)
    parsed_kinds = _normalize_kinds(kinds)
    if not parsed_kinds:
        parsed_kinds = ("http", "mcp", "grpc", "event", "websocket")

    buckets: dict[str, list[dict[str, Any]]] = {
        "http_routes": [],
        "mcp_tools": [],
        "grpc_endpoints": [],
        "event_handlers": [],
        "websocket": [],
    }
    # Per-edge-type slice — silent truncation at limit=2000 would hide
    # contracts on a large API surface. Counter each kind so the agent
    # knows if the slice was complete.
    # G5: was 2000; default invocation blew past MCP token cap (106KB).
    # 200 per-edge-type bucket keeps the typical envelope well under
    # ~10K tokens; callers needing more can paginate.
    _CONTRACT_BUCKET_LIMIT = 200
    per_kind_truncated: dict[str, bool] = {}
    for edge_type in ("handles_route", "handles_tool", "handles_event"):
        edges_slice = be.list_edges(edge_types=(edge_type,), limit=_CONTRACT_BUCKET_LIMIT)
        total = _count_edges_for(be, edge_types=(edge_type,))
        per_kind_truncated[edge_type] = total > len(edges_slice)
        for edge in edges_slice:
            node = be.get_node(edge.target_uid)
            if node is None:
                continue
            md = node.metadata or {}
            kind = md.get("kind")
            if kind is None:
                # No contract sub-kind in metadata → infer from the node's
                # own kind. A node that is not a contract surface (e.g. a
                # hook reached via a handles_tool edge) is skipped, not
                # dumped into http_routes via a blind 'http' default.
                node_kind = (node.kind or "").replace("cos:", "")
                kind = {"route": "http", "mcp_tool": "mcp", "cli_command": "cli"}.get(node_kind)
                if kind is None:
                    continue
            if kind not in parsed_kinds:
                continue
            bucket_key = {
                "http": "http_routes",
                "mcp": "mcp_tools",
                "grpc": "grpc_endpoints",
                "event": "event_handlers",
                "websocket": "websocket",
            }.get(kind, "http_routes")
            buckets[bucket_key].append(
                {
                    **NodeSummary.from_node(node).to_dict(),
                    "method": (node.metadata or {}).get("method"),
                    "path": (node.metadata or {}).get("path"),
                    "framework": (node.metadata or {}).get("framework"),
                    "handler": (node.metadata or {}).get("handler"),
                    "source": edge.source_uid,
                    "confidence": edge.confidence,
                }
            )

    # W7 / R4-10: dedupe each bucket by target uid, preferring a
    # non-test source; and (unless asked) drop entries whose ONLY source
    # is a test fixture. Pre-fix the same MCP tool appeared once per
    # source file (production + every test that decorated a fake handler).
    def _dedupe_bucket(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_uid: dict[str, dict[str, Any]] = {}
        for item in items:
            uid = item.get("uid", "")
            src = item.get("source", "") or ""
            existing = by_uid.get(uid)
            if existing is None:
                by_uid[uid] = item
            elif _is_test_source(existing.get("source", "") or "") and not _is_test_source(src):
                # Replace a test-sourced entry with a production one.
                by_uid[uid] = item
        out = list(by_uid.values())
        if not include_test_sources:
            non_test = [it for it in out if not _is_test_source(it.get("source", "") or "")]
            # Keep test-only contracts only when nothing else defines them.
            if non_test:
                out = non_test
        return out

    buckets = {k: _dedupe_bucket(v) for k, v in buckets.items()}
    result_truncated = any(per_kind_truncated.values())
    return _ok(
        {"scope": scope, **buckets, "count": sum(len(v) for v in buckets.values())},
        meta={
            "backend": be.backend_id,
            "kinds": list(parsed_kinds),
            "bucket_limit": _CONTRACT_BUCKET_LIMIT,
            "result_truncated": result_truncated,
            "per_edge_type_truncated": per_kind_truncated,
            "include_test_sources": include_test_sources,
        },
    )


def _grep_string_literals(name: str, *, limit: int = 100) -> list[dict[str, Any]]:
    # check_strings path: find the symbol name INSIDE a string literal — the
    # rename targets an AST pass misses (getattr(o, "name"), config keys,
    # dynamic dispatch). ripgrep when present (respects .gitignore), bounded
    # Python walk otherwise. Quote-scoped regex keeps precision; capped at
    # `limit`. Was a permanent [] stub → check_strings was a no-op.
    if not name or len(name) < 3:
        return []  # too short → only noise
    root = _kernel._repo_root_for_paths()
    pattern = rf"""("[^"]*\b{re.escape(name)}\b[^"]*"|'[^']*\b{re.escape(name)}\b[^']*')"""
    hits: list[dict[str, Any]] = []

    import subprocess

    try:
        proc = subprocess.run(
            ["rg", "--line-number", "--no-heading", "--color", "never", "-e", pattern, str(root)],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        for raw in proc.stdout.splitlines():
            parts = raw.split(":", 2)  # <path>:<line>:<text>
            if len(parts) < 3:
                continue
            fp, ln, text = parts
            try:
                rel = Path(fp).resolve().relative_to(root).as_posix()
            except ValueError:
                rel = fp
            hits.append(
                {"file": rel, "line": int(ln) if ln.isdigit() else None, "text": text.strip()[:200]}
            )
            if len(hits) >= limit:
                break
        return hits
    except (FileNotFoundError, OSError, subprocess.SubprocessError) as exc:
        logger.debug("rg string-scan unavailable, walking instead: %s", exc)

    # Fallback — bounded Python walk with the same filters as the indexer.
    try:
        import fnmatch

        from ..ingest.base import (
            DEFAULT_EXCLUDE,
            DEFAULT_EXCLUDE_PATHS,
            DEFAULT_INCLUDE,
        )

        rx = re.compile(pattern)
        scanned = 0
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in DEFAULT_EXCLUDE]
            # Prune path-segment excludes (tests/golden scaffold mirrors) the
            # same way walk_local does, so the fallback doesn't surface string
            # hits from duplicate-spine fixtures.
            rel_dir = Path(dirpath).resolve().relative_to(root).as_posix()
            if any(rel_dir == p or rel_dir.startswith(p + "/") for p in DEFAULT_EXCLUDE_PATHS):
                dirnames[:] = []
                continue
            for fn in filenames:
                if not any(fnmatch.fnmatchcase(fn, p) for p in DEFAULT_INCLUDE):
                    continue
                full = Path(dirpath) / fn
                if full.is_symlink():
                    continue
                scanned += 1
                if scanned > 5000:
                    return hits
                try:
                    if full.stat().st_size > 1_000_000:
                        continue
                    with full.open(encoding="utf-8", errors="ignore") as fh:
                        for i, line in enumerate(fh, 1):
                            if name in line and rx.search(line):
                                hits.append(
                                    {
                                        "file": full.resolve().relative_to(root).as_posix(),
                                        "line": i,
                                        "text": line.strip()[:200],
                                    }
                                )
                                if len(hits) >= limit:
                                    return hits
                except OSError:
                    continue
    except Exception as exc:  # fail-open — string scan is best-effort
        logger.debug("string-literal walk failed: %s", exc)
    return hits


def cos_graph_diff(
    *,
    base: str = "HEAD~1",
    head: str = "HEAD",
    analyze_downstream: bool = True,
    backend: str | None = None,
) -> dict[str, Any]:
    """Graph blast-radius of a git range — base..head changed files → affected symbols + downstream."""
    import subprocess

    base = str(base).strip()
    head = str(head).strip() or "HEAD"
    if not base:
        return _fail("validation", "base ref required")
    # Validate refs are plain git revisions (no shell-injection metachars).
    if not all(re.match(r"^[\w./~^@{}-]+$", r) for r in (base, head)):
        return _fail("validation", "base/head must be plain git revisions")
    root = _kernel._repo_root_for_paths()
    rng = f"{base}..{head}"
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "diff", "--name-only", rng],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:
        return _fail("internal", f"git diff failed: {exc}")
    if out.returncode != 0:
        return _fail("not_found", f"git diff {rng}: {out.stderr.strip()[:200]}", retryable=False)
    files = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
    if not files:
        return _ok(
            {
                "range": rng,
                "file_count": 0,
                "files": [],
                "symbols": [],
                "downstream_consumers": [],
                "downstream_tasks": [],
                "risk_level": "none",
            },
            meta={"layer": "graph", "range": rng, "file_count": 0},
        )
    # DRY: delegate to detect_changes for the blast-radius. Its data already
    # carries scope=range + files; downstream_consumers/risk come for free.
    return cos_graph_detect_changes(
        files=files,
        scope=rng,
        analyze_downstream=analyze_downstream,
        backend=backend,
    )
