"""Document RAG search and doc-header cos_* tools."""

from __future__ import annotations

from pathlib import Path

from _server_runtime import _db_conn, mcp
from database import project_root
from tools._shared import fail, ok, safe_tool
from tools.docs import doc_search, list_doc_headers, parse_doc_header
from tools.retrieve import log_retrieval, log_router_decision


# ---------------------------------------------------------------------------
# Document RAG search
# ---------------------------------------------------------------------------
@mcp.tool(
    name="cos_doc_search",
    annotations={
        "title": "Search Project Documentation",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_doc_search(
    query: str,
    source_types: str = "",
    limit: int = 5,
    mode: str = "auto",
    domain: str = "",
    layer: str = "",
    since_iso: str = "",
    include_inactive: bool = False,
    auto_context: bool = True,
) -> str:
    """Semantic + lexical search over project documentation chunks.

    Stage-1 metadata pre-filter (since migration v22):
    `domain`, `layer`, `since_iso`, and `include_inactive` narrow the
    chunk universe BEFORE vector / FTS ranking. Vector search finds
    meaning; metadata enforces reality (correct era, correct domain,
    not superseded). Combine with `source_types` for cheap, indexed
    pre-filtering.

    Args:
        query: Natural language search query (e.g. "commission rate calculation").
        source_types: Optional comma-separated filter — restrict to specific
            source types (e.g. "prd,architecture,adr"). Empty = all types.
        limit: Maximum results (1-50, default 5).
        mode: "auto" (default) | "semantic" | "lexical".
        domain: Frontmatter `domain:` filter (BACKEND, FRONTEND, OPS,
            DOCS, …). Empty = any. Indexed.
        layer: Frontmatter `layer:` filter (adr, playbook, spec, policy,
            reference, runbook, postmortem, task). Empty = any. Indexed.
        since_iso: Lower bound on frontmatter `updated:` (YYYY-MM-DD).
            Use when the agent asks about "recent" or "current" state and
            a stale older doc would be the wrong answer. Empty = any age.
        include_inactive: When False (default), hide chunks marked
            is_active=0 because the source doc was deleted or superseded.
            Set True for decision-history retrieval that must surface
            superseded specs.
        auto_context: When True (default), soft-default `domain` from the
            active task's swimlane ($COS_AGENT_DIR/.swimlane). Explicit
            `domain` argument always wins. Set False to disable.

    Response meta carries `filter_hints` — heuristic suggestions
    extracted from the query (date phrasing, domain keywords, layer
    cues). Suggestions are NEVER auto-applied; the agent decides
    whether to re-query with them. Mental model: Filter → Search →
    Summarize. Vector finds meaning, metadata enforces correctness.

    Returns:
        str: JSON envelope with results list and count. Each result
             carries source_path, source_type, heading_path, content,
             score, priority, mtime, chunk_index, retrieval_source.
    """
    types = [t.strip() for t in source_types.split(",") if t.strip()] or None
    mode_clean = mode if mode in ("auto", "semantic", "lexical") else "auto"
    domain_clean = domain.strip() or None
    layer_clean = layer.strip() or None
    since_clean = since_iso.strip() or None

    results, search_meta = doc_search(
        _db_conn,
        query=query,
        source_types=types,
        limit=limit,
        mode=mode_clean,
        domain=domain_clean,
        layer=layer_clean,
        since_iso=since_clean,
        include_inactive=include_inactive,
        auto_context=auto_context,
        return_meta=True,
    )
    # Derive retrieval source from result rows for diagnostic meta.
    if results:
        sources_used = sorted(
            {r.get("retrieval_source") for r in results if r.get("retrieval_source")}
        )
        source_label = "+".join(sources_used) if sources_used else mode_clean
    else:
        source_label = "empty"
    # Outcome-feedback loop logging.
    rids = log_retrieval(_db_conn, layer="docs", query=query, rows=results)
    # Router-level telemetry.
    log_router_decision(
        _db_conn, query=query, chosen_layer="docs", bytes_returned=len(str(results))
    )
    # D7-F4: when the rag embedding extra is unavailable, retrieval
    # silently degrades to FTS-only — surface that as retrieval_mode so the
    # beginner persona is warned, not misled. An explicit lexical request keeps
    # its own mode (intentional, not a degradation).
    from embeddings import is_available as _emb_available

    retrieval_mode = mode_clean if _emb_available() else "lexical-only"
    return ok(
        {"results": results, "count": len(results), "retrieval_ids": rids},
        meta={
            "layer": "docs",
            "query": query,
            "mode": mode_clean,
            "retrieval_mode": retrieval_mode,
            "source": source_label,
            "filters_applied": search_meta.get("applied", {}),
            "filter_hints": search_meta.get("filter_hints", {}),
        },
    )


# ---------------------------------------------------------------------------
# Doc header tools: header-only lazy load
# ---------------------------------------------------------------------------
@mcp.tool(
    name="cos_doc_header",
    annotations={
        "title": "Read Doc Header (frontmatter + opening block)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_doc_header(path: str) -> str:
    """Return a single doc's header without reading the body."""
    candidate = (path or "").strip()
    if not candidate:
        return fail("validation", "path is required")
    root_dir = project_root().resolve()
    target = Path(candidate)
    if not target.is_absolute():
        target = (root_dir / target).resolve()
    else:
        try:
            target = target.resolve()
        except OSError as exc:
            return fail("validation", f"cannot resolve path: {exc}")
    # Path-traversal guard. The MCP server is trusted today,
    # but a future external client must never read files outside the
    # project root via this tool.
    try:
        target.relative_to(root_dir)
    except ValueError:
        return fail(
            "permission",
            f"path escapes project root: {candidate}",
        )
    if not target.exists():
        return fail("not_found", f"no such file: {candidate}")
    header = parse_doc_header(target)
    if header is None:
        return fail("validation", f"cannot parse doc header: {candidate}")
    return ok(
        header,
        meta={"layer": "docs", "source": "filesystem", "query": candidate},
    )


@mcp.tool(
    name="cos_doc_headers_by",
    annotations={
        "title": "List Doc Headers by Frontmatter Filter",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_doc_headers_by(
    domain: str = "",
    layer: str = "",
    ssot: str = "",
    since_iso: str = "",
    root: str = "docs",
    limit: int = 50,
) -> str:
    """Bulk header-only scan filtered by frontmatter."""
    cap = max(1, min(int(limit) if limit else 50, 200))
    root_dir = project_root().resolve()
    root_path = Path(root) if root else Path("docs")
    if not root_path.is_absolute():
        root_path = (root_dir / root_path).resolve()
    else:
        try:
            root_path = root_path.resolve()
        except OSError as exc:
            return fail("validation", f"cannot resolve root: {exc}")
    # Path-traversal guard — root must stay inside project.
    try:
        root_path.relative_to(root_dir)
    except ValueError:
        return fail("permission", f"root escapes project root: {root}")
    if not root_path.exists():
        return fail("not_found", f"no such root: {root}")
    rows = list_doc_headers(
        root_path,
        domain=domain or None,
        layer=layer or None,
        ssot=ssot or None,
        since_iso=since_iso or None,
        limit=cap,
    )
    return ok(
        {"results": rows, "count": len(rows)},
        meta={
            "layer": "docs",
            "source": "filesystem",
            "filters_applied": {
                k: v
                for k, v in {
                    "domain": domain,
                    "layer": layer,
                    "ssot": ssot,
                    "since_iso": since_iso,
                    "root": str(root_path),
                }.items()
                if v
            },
        },
    )
