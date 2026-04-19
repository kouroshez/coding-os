#!/usr/bin/env python3
"""
Coding OS — Thinking OS MCP Server (stdio transport).

Agent-agnostic self-learning system for AI coding agents.
Tools are organized into modules under tools/:
  - memory.py   — search, timeline, details, promote
  - metrics.py  — record, query, trend
  - learning.py — extract, suggest, validate, feedback, narrative
  - routing.py  — model routing, skill routing
"""

from __future__ import annotations

import json
import logging
import sys

from mcp.server.fastmcp import FastMCP

from db import get_db_stats, init_db
from tools._shared import ok, safe_tool

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,  # MCP stdio uses stdout for protocol — logs go to stderr
)
logger = logging.getLogger("thinking_os")

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------
mcp = FastMCP("coding_os_mcp")

# ---------------------------------------------------------------------------
# Database bootstrap
# ---------------------------------------------------------------------------
_db_conn = init_db()

# Phase G.9 — opt-in continuous indexer. No-op unless COS_BACKGROUND_INDEX=1.
# Wrapped in try/except so a broken indexer never blocks MCP startup.
try:
    from background import maybe_start_indexer  # noqa: WPS433 — intentional late bind
    _bg_status = maybe_start_indexer()
    if _bg_status.get("started"):
        logger.info("background indexer started: %s", _bg_status.get("reason"))
except Exception as exc:  # noqa: BLE001 — never fail MCP boot on indexer glitch
    logger.warning("background indexer bootstrap failed: %s", exc)


# ---------------------------------------------------------------------------
# Health check tool
# ---------------------------------------------------------------------------
@mcp.tool(
    name="cos_health",
    annotations={
        "title": "Thinking OS Health Check",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def thinking_os_health() -> str:
    """Return database health stats: row counts per table, schema version, DB size, FTS5 availability, embeddings status.

    Use this tool to verify the thinking-os database is operational and
    to get a quick summary of stored data volume.

    Returns:
        str: JSON object with keys: tables (row counts), schema_version,
             fts5_available, db_size_bytes, rag (embeddings + doc_chunks status).
    """
    stats = get_db_stats(_db_conn)

    # Phase B: surface RAG availability so the agent can decide whether
    # semantic search is wired up before issuing cos_doc_search.
    embeddings_available = False
    try:
        from embeddings import is_available  # noqa: WPS433 — lazy keeps server start fast
        embeddings_available = is_available()
    except ImportError as exc:
        logger.debug("Embeddings module unavailable for health check: %s", exc)

    stats["rag"] = {
        "embeddings_available": embeddings_available,
        "embedding_model": "all-MiniLM-L6-v2",
        "embeddings_count": stats["tables"].get("embeddings") or 0,
        "document_chunks_count": stats["tables"].get("document_chunks") or 0,
    }

    # Phase C: task store status — lets the agent detect whether
    # `cos_task_*` queries will return data before making the call.
    stats["task_store"] = {
        "tasks_count": stats["tables"].get("tasks") or 0,
    }

    # Phase G.9: background indexer status — surfaced even when the loop
    # is disabled so `cos doctor` can warn about misconfigured state.
    try:
        from background import get_indexer, is_enabled  # noqa: WPS433 — lazy import keeps boot fast
        stats["background_indexer"] = get_indexer().status() if is_enabled() else {
            "enabled": False, "running": False, "reason": "COS_BACKGROUND_INDEX not set",
        }
    except ImportError as exc:  # pragma: no cover — defensive
        logger.debug("background module unavailable: %s", exc)
        stats["background_indexer"] = {"enabled": False, "running": False,
                                        "reason": f"import_error: {exc}"}

    return ok(stats, meta={"layer": "health"})


# ---------------------------------------------------------------------------
# Import tool modules
# ---------------------------------------------------------------------------
from graph import query_related
from tools.docs import doc_search
from tools.learning import generate_feedback_drafts, learn_extract, learn_narrative, learn_suggest, learn_validate
from tools.memory import memory_details, memory_promote, memory_search, memory_timeline
from tools.metrics import metric_query, metric_record, metric_trend
from tools.retrieve import cite_retrievals, learn_from_retrievals, log_retrieval
from tools.routing import route_model, route_skill
from tools.tasks import task_by_filter, task_dependencies, task_dependents, task_search


# ---------------------------------------------------------------------------
# Metrics tools (TASK-143)
# ---------------------------------------------------------------------------
@mcp.tool(
    name="cos_metric_record",
    annotations={
        "title": "Record Agent Metric",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_metric_record(
    agent_type: str,
    outcome: str,
    task_id: str = "",
    model: str = "",
    duration_ms: int = 0,
    domain: str = "",
    complexity: str = "",
) -> str:
    """Record a single agent performance metric after task completion.

    Args:
        agent_type: Type of agent (e.g. "general", "planner", "code-reviewer").
        outcome: Result — one of: success, rework, partial, blocked.
        task_id: Task identifier (e.g. "TASK-143"). Optional.
        model: Model used (e.g. "sonnet", "opus"). Optional.
        duration_ms: Duration in milliseconds. Optional.
        domain: Task domain (e.g. "BACKEND", "FRONTEND", "INFRA"). Optional.
        complexity: Cynefin classification (e.g. "CLEAR", "COMPLICATED"). Optional.

    Returns:
        str: JSON with inserted row id and status.
    """
    result = metric_record(
        _db_conn,
        task_id=task_id or None,
        agent_type=agent_type,
        model=model or None,
        duration_ms=duration_ms or None,
        outcome=outcome,
        domain=domain or None,
        complexity=complexity or None,
    )
    return ok(result, meta={"layer": "metrics"})


@mcp.tool(
    name="cos_metric_query",
    annotations={
        "title": "Query Agent Metrics",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_metric_query(
    domain: str = "",
    model: str = "",
    outcome: str = "",
    agent_type: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 20,
) -> str:
    """Query agent metrics with optional filters.

    Args:
        domain: Filter by domain (e.g. "BACKEND"). Optional.
        model: Filter by model (e.g. "sonnet"). Optional.
        outcome: Filter by outcome (e.g. "rework"). Optional.
        agent_type: Filter by agent type. Optional.
        date_from: Start date (ISO format, e.g. "2026-03-01"). Optional.
        date_to: End date (ISO format, e.g. "2026-03-25"). Optional.
        limit: Max rows (1-100, default 20).

    Returns:
        str: JSON with total count and matching rows.
    """
    result = metric_query(
        _db_conn,
        domain=domain or None,
        model=model or None,
        outcome=outcome or None,
        agent_type=agent_type or None,
        date_from=date_from or None,
        date_to=date_to or None,
        limit=limit,
    )
    return ok(result, meta={"layer": "metrics", "filters_applied": {
        "domain": domain or None, "model": model or None, "outcome": outcome or None,
        "agent_type": agent_type or None,
    }})


@mcp.tool(
    name="cos_metric_trend",
    annotations={
        "title": "Agent Metric Trends",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_metric_trend(
    metric: str = "success_rate",
    window_days: int = 30,
    group_by: str = "domain",
) -> str:
    """Get aggregated trend data for agent metrics.

    Args:
        metric: One of: success_rate, rework_rate, count.
        window_days: Lookback window in days (1-365, default 30).
        group_by: Grouping dimension: domain, model, agent_type, complexity.

    Returns:
        str: JSON with trends array containing period, counts, and rate.
    """
    result = metric_trend(
        _db_conn,
        metric=metric,
        window_days=window_days,
        group_by=group_by,
    )
    return ok(result, meta={"layer": "metrics"})


# ---------------------------------------------------------------------------
# Memory tools (TASK-142)
# ---------------------------------------------------------------------------
@mcp.tool(
    name="cos_search",
    annotations={
        "title": "Search Thinking OS Memory",
        "readOnlyHint": False,  # updates access_count
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
@safe_tool
def thinking_os_search(
    query: str,
    limit: int = 5,
    memory_type: str = "",
) -> str:
    """Search observations and learned patterns with 5-signal ranking.

    Use during Orient step to find relevant past experience.
    Updates access_count and confidence on retrieved results.

    Args:
        query: Search text (e.g. "backend rework", "django migration").
        limit: Max results (1-20, default 5).
        memory_type: Filter by type (pattern/workflow/error/decision/discovery). Optional.

    Returns:
        str: JSON with results list [{id, title, confidence, impact_score, memory_type, source_table}].
    """
    from db import has_fts5_table
    result = memory_search(
        _db_conn,
        query=query,
        limit=limit,
        memory_type=memory_type or None,
        use_fts5=has_fts5_table(_db_conn),
    )
    # Phase G.8 — log each returned row for the outcome-feedback loop.
    rids = log_retrieval(
        _db_conn, layer="memory", query=query,
        rows=(result.get("results") or []) if isinstance(result, dict) else [],
    )
    if isinstance(result, dict):
        result["retrieval_ids"] = rids
    return ok(result, meta={"layer": "memory", "query": query,
                            "source": result.get("source") if isinstance(result, dict) else None})


@mcp.tool(
    name="cos_timeline",
    annotations={
        "title": "Thinking OS Timeline",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def thinking_os_timeline(
    days: int = 30,
    domain: str = "",
    limit: int = 20,
) -> str:
    """Get recent task outcomes and observations timeline.

    Args:
        days: Lookback window (1-365, default 30).
        domain: Filter by domain (e.g. "BACKEND"). Optional.
        limit: Max entries (1-50, default 20).

    Returns:
        str: JSON with timeline entries [{id, title, date, outcome, type}].
    """
    result = memory_timeline(
        _db_conn,
        days=days,
        domain=domain or None,
        limit=limit,
    )
    return ok(result, meta={"layer": "memory",
                            "filters_applied": {"domain": domain or None, "days": days}})


@mcp.tool(
    name="cos_details",
    annotations={
        "title": "Thinking OS Details",
        "readOnlyHint": False,  # updates access_count
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
@safe_tool
def thinking_os_details(
    pattern_id: int,
    source: str = "learned_patterns",
) -> str:
    """Get full details of a pattern, observation, or task outcome.

    Args:
        pattern_id: Row ID (or task_id string for task_outcomes).
        source: Table name — observations, learned_patterns, or task_outcomes.

    Returns:
        str: JSON with full record.
    """
    result = memory_details(
        _db_conn,
        pattern_id=pattern_id,
        source=source,
    )
    return ok(result, meta={"layer": "memory"})


@mcp.tool(
    name="cos_promote",
    annotations={
        "title": "Promote Pattern to Rule",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def thinking_os_promote_tool(
    pattern_id: int,
    target: str = "feedback",
) -> str:
    """Promote a validated pattern to a rule or feedback memory file.

    Requires confidence >= 0.3. Creates file content but does NOT write to disk
    (caller writes the returned content to the appropriate location).

    Args:
        pattern_id: ID in learned_patterns table.
        target: Output type — "feedback" or "rule".

    Returns:
        str: JSON with status, filename, and file content to write.
    """
    result = memory_promote(
        _db_conn,
        pattern_id=pattern_id,
        target=target,
        memory_dir="",  # caller handles file writing
    )
    return ok(result, meta={"layer": "memory"})


# ---------------------------------------------------------------------------
# Learning tools (TASK-144)
# ---------------------------------------------------------------------------
@mcp.tool(
    name="cos_learn_extract",
    annotations={
        "title": "Extract Learned Patterns",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_learn_extract(min_occurrences: int = 3) -> str:
    """Scan task outcomes to discover recurring patterns.

    Detects domain_rework, skill_correlation, and complexity_mismatch patterns.
    Inserts new patterns into learned_patterns with calculated confidence.

    Args:
        min_occurrences: Minimum occurrences to consider a pattern (default 3).

    Returns:
        str: JSON with extracted patterns list and analysis stats.
    """
    result = learn_extract(_db_conn, min_occurrences=min_occurrences)
    return ok(result, meta={"layer": "learning"})


@mcp.tool(
    name="cos_learn_suggest",
    annotations={
        "title": "Suggest Learned Patterns",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_learn_suggest(
    domain: str = "",
    complexity: str = "",
    task_type: str = "",
    limit: int = 5,
) -> str:
    """Return relevant patterns for the current task context.

    Includes spaced repetition: fading patterns (0.2-0.4 confidence) that
    were once validated get priority for re-validation.

    Args:
        domain: Task domain (e.g. "BACKEND"). Optional.
        complexity: Cynefin classification. Optional.
        task_type: Type of task (e.g. "feat"). Optional.
        limit: Max suggestions (1-20, default 5).

    Returns:
        str: JSON with suggestions list [{id, pattern, confidence, reason}].
    """
    result = learn_suggest(
        _db_conn,
        domain=domain or None,
        complexity=complexity or None,
        task_type=task_type or None,
        limit=limit,
    )
    return ok(result, meta={"layer": "learning",
                            "filters_applied": {"domain": domain or None,
                                                "complexity": complexity or None,
                                                "task_type": task_type or None}})


@mcp.tool(
    name="cos_learn_validate",
    annotations={
        "title": "Validate Learned Pattern",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_learn_validate(pattern_id: int, was_helpful: bool = True) -> str:
    """Record whether a suggested pattern was helpful.

    Updates confidence using brain-inspired formulas:
    - Helpful: LTP with diminishing returns + temporal proximity bonus
    - Not helpful: LTD proportional penalty

    Args:
        pattern_id: ID in learned_patterns table.
        was_helpful: Whether the pattern was useful (default True).

    Returns:
        str: JSON with old/new confidence and validation status.
    """
    result = learn_validate(_db_conn, pattern_id=pattern_id, was_helpful=was_helpful)
    return ok(result, meta={"layer": "learning"})


@mcp.tool(
    name="cos_learn_feedback",
    annotations={
        "title": "Generate Feedback Drafts",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_learn_feedback(min_rework: int = 3) -> str:
    """Detect rework clusters and generate draft feedback content.

    Scans task_outcomes for domain+skill combinations with 3+ reworks.
    Returns draft content — caller writes files and updates MEMORY.md.
    Human confirmation required before activation.

    Args:
        min_rework: Minimum rework tasks to trigger draft (default 3).

    Returns:
        str: JSON with drafts list [{filename, content, domain, skill, evidence}].
    """
    result = generate_feedback_drafts(_db_conn, min_rework=min_rework)
    return ok(result, meta={"layer": "learning"})


@mcp.tool(
    name="cos_learn_narrative",
    annotations={
        "title": "Record Breakthrough Narrative",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_learn_narrative(
    task_id: str,
    what_failed: str = "",
    what_worked: str = "",
    key_insight: str = "",
) -> str:
    """Record what was learned from a difficult task (breakthrough narrative).

    Call this after a rework→success breakthrough to capture:
    - What approaches failed and why
    - What finally worked
    - The reusable key insight

    Creates a high-impact learned pattern for future suggestions.

    Args:
        task_id: Task identifier (e.g. "TASK-100").
        what_failed: Approaches that didn't work.
        what_worked: The solution that resolved the issue.
        key_insight: Reusable lesson learned (required).

    Returns:
        str: JSON with status, history_id, pattern_id.
    """
    result = learn_narrative(
        _db_conn,
        task_id=task_id,
        what_failed=what_failed,
        what_worked=what_worked,
        key_insight=key_insight,
    )
    return ok(result, meta={"layer": "learning"})


# ---------------------------------------------------------------------------
# Graph tools (v4 brain features)
# ---------------------------------------------------------------------------
@mcp.tool(
    name="cos_graph",
    annotations={
        "title": "Query Concept/File Graph",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def thinking_os_graph(
    node: str,
    max_hops: int = 2,
    limit: int = 10,
    edge_types: str = "",
) -> str:
    """Query the concept/file relationship graph via BFS traversal.

    Finds related files and concepts within max_hops of a starting node.
    Edge types: co_edit (files modified together), concept_link (co-occurring concepts).

    Args:
        node: Starting node — file path or concept (e.g. "backend/apps/products/models.py" or "django").
        max_hops: Traversal depth (1-3, default 2).
        limit: Max results (1-50, default 10).
        edge_types: Comma-separated filter (e.g. "co_edit,concept_link"). Empty = all.

    Returns:
        str: JSON with root, nodes, edges, count.
    """
    types = [t.strip() for t in edge_types.split(",") if t.strip()] or None
    result = query_related(_db_conn, node=node, max_hops=max_hops, limit=limit, edge_types=types)
    return ok(result, meta={"layer": "graph", "query": node})


# ---------------------------------------------------------------------------
# Routing tools (TASK-145)
# ---------------------------------------------------------------------------
@mcp.tool(
    name="cos_route_model",
    annotations={
        "title": "Route Model Recommendation",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_route_model(
    complexity: str,
    dimensions: int = 1,
    domain: str = "",
) -> str:
    """Recommend optimal model based on historical outcome data.

    Cold start (<10 outcomes): returns static default from performance.md.
    Warm: queries success rates per model for the given complexity+domain.

    Args:
        complexity: Cynefin classification (CLEAR/COMPLICATED/COMPLEX/CHAOTIC).
        dimensions: Number of problem dimensions (default 1).
        domain: Task domain (e.g. "BACKEND"). Optional.

    Returns:
        str: JSON with recommended_model, confidence, reason, fallback_model.
    """
    result = route_model(
        _db_conn,
        complexity=complexity,
        dimensions=dimensions,
        domain=domain or None,
    )
    return ok(result, meta={"layer": "routing"})


@mcp.tool(
    name="cos_route_skill",
    annotations={
        "title": "Route Skill Recommendation",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_route_skill(
    domain: str,
    task_type: str = "",
    complexity: str = "",
) -> str:
    """Recommend skills based on historical outcome data.

    Cold start: returns static defaults from skill-enforcement.md.
    Warm: augments with historically successful skills.

    Args:
        domain: Task domain (e.g. "BACKEND", "FRONTEND").
        task_type: Type of task (e.g. "feat", "fix"). Optional.
        complexity: Cynefin classification. Optional.

    Returns:
        str: JSON with skills list [{name, confidence, reason}].
    """
    result = route_skill(
        _db_conn,
        domain=domain,
        task_type=task_type or None,
        complexity=complexity or None,
    )
    return ok(result, meta={"layer": "routing"})


# ---------------------------------------------------------------------------
# Document RAG search (Phase B.4)
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
) -> str:
    """Semantic search over project documentation chunks (PRD, architecture, ADRs, ...).

    Use this when you need to find a specific spec, rule, or architecture
    decision. Returns chunks (300-500 tokens each) instead of full files,
    so you load only the relevant slice of a doc.

    The chunks come from `make docs-index` which walks `docs/` and embeds
    each H2/H3 section into the document_chunks table. Source types are
    configured in `.coding-os/rag-config.yaml`.

    Args:
        query: Natural language search query (e.g. "commission rate calculation").
        source_types: Optional comma-separated filter — restrict to specific
            source types (e.g. "prd,architecture,adr"). Empty = all types.
        limit: Maximum results (1-50, default 5).

    Returns:
        str: JSON with results list and count. Each result contains:
             source_path, source_type, heading_path, content, score, priority,
             mtime, chunk_index. Empty results when embeddings unavailable
             or no matches.
    """
    types = [t.strip() for t in source_types.split(",") if t.strip()] or None
    mode_clean = mode if mode in ("auto", "semantic", "lexical") else "auto"
    results = doc_search(
        _db_conn, query=query, source_types=types, limit=limit, mode=mode_clean,
    )
    # Derive retrieval source from result rows for diagnostic meta.
    if results:
        sources_used = sorted({r.get("retrieval_source") for r in results if r.get("retrieval_source")})
        source_label = "+".join(sources_used) if sources_used else mode_clean
    else:
        source_label = "empty"
    # Phase G.8 — outcome-feedback loop logging.
    rids = log_retrieval(_db_conn, layer="docs", query=query, rows=results)
    return ok(
        {"results": results, "count": len(results), "retrieval_ids": rids},
        meta={"layer": "docs", "query": query, "mode": mode_clean,
              "source": source_label,
              "filters_applied": {"source_types": types} if types else {}},
    )


# ---------------------------------------------------------------------------
# Task store tools (Phase C.5)
# ---------------------------------------------------------------------------
@mcp.tool(
    name="cos_task_search",
    annotations={
        "title": "Search Tasks (Semantic + Filter)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_task_search(
    query: str,
    status: str = "",
    domain: str = "",
    limit: int = 10,
) -> str:
    """Semantic search over the task store with optional status/domain filters.

    Use this when you need to find tasks related to a concept — even when
    exact keywords don't match. Falls back to LIKE on title + goal when
    embeddings are unavailable.

    Args:
        query: Natural language query (e.g. "payment splitting multi vendor").
        status: Optional status filter — one of open/wip/done/blocked. Empty = all.
        domain: Optional domain filter (BACKEND/FRONTEND/DOCS/INFRA/...). Empty = all.
        limit: Maximum results (1-100, default 10).

    Returns:
        JSON with results and count. Each result: task_id, title, domain,
        status, file_path, goal_text, dependencies, score.
    """
    results = task_search(
        _db_conn,
        query=query,
        status=status or None,
        domain=domain or None,
        limit=limit,
    )
    rids = log_retrieval(_db_conn, layer="tasks", query=query, rows=results)
    return ok(
        {"results": results, "count": len(results), "retrieval_ids": rids},
        meta={"layer": "tasks", "query": query,
              "filters_applied": {"status": status or None, "domain": domain or None}},
    )


@mcp.tool(
    name="cos_task_dependencies",
    annotations={
        "title": "Task Dependencies (Upstream)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_task_dependencies(task_id: str) -> str:
    """Return the tasks that `task_id` directly depends on.

    Use before starting a task to verify prerequisites are done. Returns
    only direct (first-level) dependencies — use repeated calls for
    transitive traversal.

    Args:
        task_id: Task identifier (e.g. "TASK-199").

    Returns:
        JSON with task_id, dependencies list, and count.
    """
    results = task_dependencies(_db_conn, task_id)
    return ok({"task_id": task_id, "dependencies": results, "count": len(results)},
              meta={"layer": "tasks"})


@mcp.tool(
    name="cos_task_dependents",
    annotations={
        "title": "Task Dependents (Downstream)",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_task_dependents(task_id: str) -> str:
    """Return the tasks that declare `task_id` as a dependency.

    Use for impact analysis: "If I change TASK-195, what downstream tasks
    need to be re-verified?" Returns only direct dependents — non-transitive.

    Args:
        task_id: Task identifier (e.g. "TASK-195").

    Returns:
        JSON with task_id, dependents list, and count.
    """
    results = task_dependents(_db_conn, task_id)
    return ok({"task_id": task_id, "dependents": results, "count": len(results)},
              meta={"layer": "tasks"})


@mcp.tool(
    name="cos_task_by_filter",
    annotations={
        "title": "List Tasks by Filter",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_task_by_filter(
    status: str = "",
    domain: str = "",
    limit: int = 20,
) -> str:
    """List tasks matching an optional status and/or domain filter.

    No semantic query — pure structured filter. Use when you need "all
    open backend tasks" or "all blocked tasks" without a specific concept.

    Args:
        status: Filter by status (open/wip/done/blocked). Empty = all.
        domain: Filter by domain (BACKEND/FRONTEND/DOCS/...). Empty = all.
        limit: Maximum results (1-100, default 20).

    Returns:
        JSON with results list (sorted by task_id ASC) and count.
    """
    results = task_by_filter(
        _db_conn,
        status=status or None,
        domain=domain or None,
        limit=limit,
    )
    return ok(
        {"results": results, "count": len(results)},
        meta={"layer": "tasks",
              "filters_applied": {"status": status or None, "domain": domain or None}},
    )


# ---------------------------------------------------------------------------
# Retrieval feedback (Phase G.8)
# ---------------------------------------------------------------------------
@mcp.tool(
    name="cos_retrieval_cite",
    annotations={
        "title": "Cite Retrievals the Agent Used",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_retrieval_cite(retrieval_ids: str) -> str:
    """Mark retrieval rows as actively cited by the agent.

    Call this after using one or more chunks/patterns/tasks in a meaningful
    way (read them carefully, applied them). Cited retrievals get ~4× the
    weight when priority-learning runs, so the signal is only useful if it
    reflects actual use — do NOT cite passive retrievals.

    Args:
        retrieval_ids: Comma-separated list of retrieval ids (int), returned
            as `retrieval_ids` in prior cos_search / cos_doc_search /
            cos_task_search responses. e.g. "12,17,24".

    Returns:
        JSON with `{updated, unknown}` — updated count + list of ids that
        did not exist.
    """
    try:
        ids = [int(x) for x in retrieval_ids.split(",") if x.strip()]
    except ValueError:
        raise ValueError("retrieval_ids must be comma-separated integers")
    result = cite_retrievals(_db_conn, ids)
    return ok(result, meta={"layer": "learning"})


@mcp.tool(
    name="cos_retrieval_learn",
    annotations={
        "title": "Priority Learning from Retrieval Outcomes",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_retrieval_learn(lookback_days: int = 7, dry_run: bool = False) -> str:
    """Adjust document_chunks.priority based on recent retrieval outcomes.

    Walks retrievals with a known outcome in the lookback window and:
      - chunk cited in a success task → priority += 0.02
      - chunk cited in a rework/blocked task → priority −= 0.01
      - passive retrievals ±0.005 (weaker signal)

    Clamped to [0.1, 0.9]. Intended to run nightly via cron or after a
    batch of task-done events.

    Args:
        lookback_days: How many days of retrievals to consider (default 7).
        dry_run: When True, compute changes without writing.

    Returns:
        `{adjusted, gained, lost, changes[], status}` envelope.
    """
    result = learn_from_retrievals(_db_conn,
                                   lookback_days=int(lookback_days),
                                   dry_run=bool(dry_run))
    return ok(result, meta={"layer": "learning"})


# ---------------------------------------------------------------------------
# Agent digest (Phase G.10)
# ---------------------------------------------------------------------------
@mcp.tool(
    name="cos_digest_regenerate",
    annotations={
        "title": "Regenerate Agent Digest",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_digest_regenerate(project_root: str = "") -> str:
    """Refresh `.coding-os/digest.md` from current memory state.

    The digest is a ≤ 2.4 KB rolling snapshot of the agent's identity:
    active beliefs, fading patterns, recent breakthroughs, preferences.
    Session-startup reads this file to give the agent a coherent
    memory anchor before any retrieval fires.

    Args:
        project_root: Override project root. Empty (default) uses cwd.

    Returns:
        `{path, size_chars, truncated, status}` envelope.
    """
    import os
    from pathlib import Path
    from digest import regenerate

    root = Path(project_root) if project_root else Path(
        os.environ.get("COS_PROJECT_ROOT", ".")
    )
    result = regenerate(_db_conn, project_root=root)
    return ok(result, meta={"layer": "learning"})


# ---------------------------------------------------------------------------
# Retrieval quality / enrichment gate (Phase G.11)
# ---------------------------------------------------------------------------
@mcp.tool(
    name="cos_retrieval_quality",
    annotations={
        "title": "Retrieval Precision Summary",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_retrieval_quality(lookback_days: int = 14, layer: str = "") -> str:
    """Report mean retrieval precision over the lookback window.

    Precision is derived from (was_cited, outcome) pairs on the
    retrievals table, so it's honest: a retrieval that was cited and
    led to success counts as 1.0; a cited retrieval that led to rework
    counts as 0.0. Used to decide whether contextual enrichment is worth
    the LLM cost.

    Args:
        lookback_days: Window in days (default 14).
        layer: Optional layer filter ("memory"|"docs"|"tasks").

    Returns:
        `{mean_precision, samples, below_gate, gate, layer, status}`.
    """
    from retrieval_quality import backfill_quality_from_outcomes, precision_summary

    # Idempotent: ensure quality rows are up to date before summarising
    backfill_quality_from_outcomes(_db_conn, lookback_days=int(lookback_days))
    result = precision_summary(
        _db_conn, lookback_days=int(lookback_days), layer=layer or None,
    )
    return ok(result, meta={"layer": "metrics"})


@mcp.tool(
    name="cos_retrieval_enrichment_check",
    annotations={
        "title": "Contextual Enrichment Recommendation",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_retrieval_enrichment_check(lookback_days: int = 14) -> str:
    """Recommend whether to enable contextual retrieval enrichment.

    The underlying LLM enrichment path is intentionally a stub — this tool
    exists so the *decision* is metric-driven and auditable before anyone
    pays the Haiku bill.

    Args:
        lookback_days: Window of retrieval quality data (default 14).

    Returns:
        `{recommend: bool, reason, cost_warning?, summary}`.
    """
    from retrieval_quality import backfill_quality_from_outcomes, should_enable_enrichment

    backfill_quality_from_outcomes(_db_conn, lookback_days=int(lookback_days))
    result = should_enable_enrichment(_db_conn, lookback_days=int(lookback_days))
    return ok(result, meta={"layer": "metrics"})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def _run_self_test() -> bool:
    """Quick self-test: verify DB is reachable and health tool works.

    Walks the MCP envelope (docs/engineering/mcp-error-envelope.md) — asserts
    `ok: true` then drills into `data` for the actual health stats.
    """
    logger.info("Running self-test...")
    envelope = json.loads(thinking_os_health())

    if not envelope.get("ok"):
        logger.error("FAIL: health returned error envelope: %s", envelope.get("error"))
        return False

    data = envelope["data"]
    checks_passed = True

    if "schema_version" not in data:
        logger.error("FAIL: schema_version missing from health response")
        checks_passed = False
    elif data["schema_version"] < 1:
        logger.error("FAIL: schema_version is %d, expected >= 1", data["schema_version"])
        checks_passed = False

    if "tables" not in data:
        logger.error("FAIL: tables missing from health response")
        checks_passed = False
    else:
        expected_tables = [
            "task_outcomes", "agent_metrics", "learned_patterns",
            "experiment_log", "observations", "session_summaries",
        ]
        for table in expected_tables:
            if table not in data["tables"]:
                logger.error("FAIL: table '%s' missing from stats", table)
                checks_passed = False
            elif data["tables"][table] is None:
                logger.error("FAIL: table '%s' does not exist in DB", table)
                checks_passed = False

    if checks_passed:
        logger.info("PASS: all self-test checks passed")
        logger.info("Stats: %s", json.dumps(data, indent=2))
    return checks_passed


def main() -> None:
    """Entry point — handles --test flag or starts MCP stdio server."""
    if "--test" in sys.argv:
        success = _run_self_test()
        sys.exit(0 if success else 1)
    else:
        logger.info("Starting thinking-os MCP server (stdio)...")
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
