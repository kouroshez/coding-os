"""
Coding OS — Document RAG search tool.

Provides `doc_search` — semantic search over the `document_chunks` table
populated by `doc_indexer`. Returns chunk-level results (300-500 tokens each)
with heading_path metadata so the agent can fetch only the relevant slice
of a doc instead of full-reading it.

Public API:
    doc_search(conn, query, source_types, limit, threshold, dedupe_per_source)
        -> list[dict]

Module layout:
  _docs_hints      query heuristics + active-task context (soft filters)
  _docs_retrieval  the semantic / lexical passes and their metadata pre-filter
  _docs_headers    frontmatter + opening-block parsing for the header tools
  this module      doc_search — the routing, dedupe and meta assembly on top
"""

from __future__ import annotations

import logging
import sqlite3

from ._docs_headers import (
    _BULK_MAX_RESULTS as _BULK_MAX_RESULTS,
    _FRONTMATTER_RE as _FRONTMATTER_RE,
    _H1_RE as _H1_RE,
    _HEADER_READ_BYTES as _HEADER_READ_BYTES,
    _LONG_OPENING_RE as _LONG_OPENING_RE,
    _SHORT_OPENING_RE as _SHORT_OPENING_RE,
    _parse_frontmatter_block as _parse_frontmatter_block,
    _parse_opening_block as _parse_opening_block,
    list_doc_headers as list_doc_headers,
    parse_doc_header as parse_doc_header,
)
from ._docs_hints import (
    _BARE_YEAR_RE as _BARE_YEAR_RE,
    _DOMAIN_HINTS as _DOMAIN_HINTS,
    _IDENTIFIER_RE as _IDENTIFIER_RE,
    _LAYER_HINTS as _LAYER_HINTS,
    _RECENCY_HINTS as _RECENCY_HINTS,
    _SWIMLANE_DOMAIN as _SWIMLANE_DOMAIN,
    _YEAR_RE as _YEAR_RE,
    SearchMode,
    _active_task_context,
    _suggest_filters_from_query,
    looks_like_identifier,
)
from ._docs_retrieval import (
    _OVERFETCH_MULTIPLIER as _OVERFETCH_MULTIPLIER,
    _build_metadata_filter as _build_metadata_filter,
    _fts_hydrate as _fts_hydrate,
    _lexical_search,
    _like_hydrate as _like_hydrate,
    _resolve_doc_threshold,
    _semantic_search,
)

logger = logging.getLogger("coding_os.tools.docs")

# Default per-source dedupe cap when dedupe_per_source=True. Two chunks per
# source file is the sweet spot — enough for a section + neighbor without
# crowding the result list.
_MAX_PER_SOURCE = 2


def doc_search(
    conn: sqlite3.Connection,
    query: str,
    source_types: list[str] | None = None,
    limit: int = 5,
    threshold: float | None = None,
    dedupe_per_source: bool = True,
    mode: SearchMode = "auto",
    *,
    domain: str | None = None,
    layer: str | None = None,
    since_iso: str | None = None,
    include_inactive: bool = False,
    auto_context: bool = True,
    return_meta: bool = False,
) -> list[dict] | tuple[list[dict], dict]:
    """Semantic + lexical search over project documentation chunks.

    Stage-1 metadata pre-filter (since migration v22): the optional
    `domain`, `layer`, `since_iso`, and `include_inactive` arguments
    narrow the chunk universe BEFORE vector / FTS ranking. This is the
    "metadata enforces reality" half of production RAG — vector finds
    meaning, metadata decides which docs are even allowed to compete.

    Args:
        conn: Open SQLite connection (must include migration v5+; v9 adds
            the document_chunks_fts table; v22 adds frontmatter columns).
        query: Natural language query (e.g. "commission rate calculation").
        source_types: Optional filter — only return chunks whose source_type
            matches one of these values (e.g. ["prd", "architecture"]).
        limit: Maximum results to return (1-50).
        threshold: Minimum cosine similarity. Default None → the active
            model's doc-calibrated floor (MiniLM 0.05 / BGE-M3 0.50); pass an
            explicit float to override.
        dedupe_per_source: When True, return at most _MAX_PER_SOURCE chunks
            per source_path so a single dominant file doesn't crowd out others.
        mode: Retrieval mode:
            - "auto"     → identifier-looking query → FTS first, else semantic;
                           fall back to the other on empty.
            - "semantic" → embeddings-only (legacy behavior).
            - "lexical"  → FTS5 match only (no embedding even if available).
        domain: Pre-filter on docs/governance/docs-system.md frontmatter
            domain field (BACKEND, FRONTEND, OPS, DOCS, …). None = any.
        layer: Pre-filter on frontmatter layer (adr, playbook, spec,
            policy, reference, runbook, postmortem, task). None = any.
        since_iso: Lower bound on frontmatter `updated:` (YYYY-MM-DD).
            Useful when an agent asks about "recent" / "current" state and
            stale older docs would be a wrong answer. None = any age.
        include_inactive: When False (default), hide chunks whose row was
            marked is_active=0 because the source doc was deleted or
            superseded. Set True to surface superseded specs.
        auto_context: When True (default) AND `domain` was not passed
            explicitly, read the active task's swimlane from
            $COS_AGENT_DIR/.swimlane and apply it as the default domain
            filter. Soft default — never overrides an explicit `domain=`
            argument. Set False for predictable test behavior.
        return_meta: When True, returns (results, meta) tuple where meta
            carries `filter_hints` (heuristic suggestions extracted from
            the query) and `applied` (which filters actually ran). Keeps
            the legacy list-only return shape when False (default).

    Returns:
        List of result dicts (or `(results, meta)` when `return_meta=True`).
        Each result carries a `retrieval_source` field so callers / audit
        can tell whether the row came from semantic or lexical.
    """
    if not query or not query.strip():
        return ([], {"filter_hints": {}, "applied": {}}) if return_meta else []

    # Cap inputs to defensive limits
    limit = max(1, min(int(limit), 50))

    if threshold is None:
        threshold = _resolve_doc_threshold()

    # Soft defaults from active task context. Explicit kwargs always win.
    applied_domain = domain
    if auto_context and applied_domain is None:
        ctx = _active_task_context()
        applied_domain = ctx.get("domain")

    results: list[dict] = []

    md_kwargs = {
        "source_types": source_types,
        "domain": applied_domain,
        "layer": layer,
        "since_iso": since_iso,
        "include_inactive": include_inactive,
    }

    if mode == "lexical":
        results = _lexical_search(conn, query, limit, **md_kwargs)
    elif mode == "semantic":
        results = _semantic_search(conn, query, limit, threshold, **md_kwargs)
    else:  # auto
        # Identifier-looking → FTS first; else semantic first.
        identifier_first = looks_like_identifier(query)
        if identifier_first:
            results = _lexical_search(conn, query, limit, **md_kwargs)
            if not results:
                results = _semantic_search(conn, query, limit, threshold, **md_kwargs)
        else:
            results = _semantic_search(conn, query, limit, threshold, **md_kwargs)
            if not results:
                results = _lexical_search(conn, query, limit, **md_kwargs)

    if dedupe_per_source:
        per_source_count: dict[str, int] = {}
        deduped: list[dict] = []
        for item in results:
            count = per_source_count.get(item["source_path"], 0)
            if count >= _MAX_PER_SOURCE:
                continue
            per_source_count[item["source_path"]] = count + 1
            deduped.append(item)
        results = deduped

    final = results[:limit]
    if not return_meta:
        return final

    applied = {
        k: v
        for k, v in {
            "source_types": source_types,
            "domain": applied_domain,
            "layer": layer,
            "since_iso": since_iso,
            "include_inactive": include_inactive or None,
            "auto_context": auto_context or None,
        }.items()
        if v is not None
    }
    meta = {
        "filter_hints": _suggest_filters_from_query(query),
        "applied": applied,
    }
    return final, meta
