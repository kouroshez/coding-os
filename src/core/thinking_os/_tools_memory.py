"""Metric, memory, and learning cos_* tools registered on the shared server."""

from __future__ import annotations

from _server_runtime import (
    _db_conn,
    _persist_learn_suggestions_safe,
    _record_memory_check_safe,
    mcp,
)
from tools._shared import fail, ok, safe_tool
from tools.learning import learn_extract, learn_narrative, learn_suggest, learn_validate
from tools.logs import log_query
from tools.memory import memory_details, memory_promote, memory_search, memory_timeline
from tools.metrics import metric_query, metric_record, metric_trend
from tools.retrieve import log_retrieval, log_router_decision


# ---------------------------------------------------------------------------
# Metrics tools
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
    return ok(
        result,
        meta={
            "layer": "metrics",
            "filters_applied": {
                "domain": domain or None,
                "model": model or None,
                "outcome": outcome or None,
                "agent_type": agent_type or None,
            },
        },
    )


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


@mcp.tool(
    name="cos_log_query",
    annotations={
        "title": "Query Durable Error / Log Store",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_log_query(
    level: str = "",
    scope: str = "",
    since: str = "",
    search: str = "",
    session_id: str = "",
    trace_id: str = "",
    fingerprint: str = "",
    limit: int = 50,
) -> str:
    """Query the durable log_events store (WARN+), most-recent first — the agent's "what is broken now"."""
    result = log_query(
        _db_conn,
        level=level or None,
        scope=scope or None,
        since=since or None,
        search=search or None,
        session_id=session_id or None,
        trace_id=trace_id or None,
        fingerprint=fingerprint or None,
        limit=limit,
    )
    return ok(result, meta={"layer": "logs", "source": "cos_log_query"})


# ---------------------------------------------------------------------------
# Memory tools
# ---------------------------------------------------------------------------
@mcp.tool(
    name="cos_observation_record",
    annotations={
        "title": "Record Observation (manual capture)",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_observation_record(
    file_path: str,
    tool_name: str = "Edit",
) -> str:
    """Record an observation explicitly."""
    from capture import capture_observation

    tool_name = (tool_name or "Edit").strip()
    if tool_name not in {"Write", "Edit", "MultiEdit"}:
        return fail("validation", f"tool_name must be Write|Edit|MultiEdit, got {tool_name!r}")
    if not file_path:
        return fail("validation", "file_path is required")
    payload = {"tool_name": tool_name, "tool_input": {"file_path": file_path}}
    result = capture_observation(payload)
    return ok(result, meta={"layer": "memory", "source": "cos_observation_record"})


@mcp.tool(
    name="cos_search",
    annotations={
        "title": "Search Thinking OS Memory",
        "readOnlyHint": False,  # writes retrieval telemetry only — raw search does NOT bump access_count/confidence
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
@safe_tool(name="cos_search")
def thinking_os_search(
    query: str,
    limit: int = 5,
    memory_type: str = "",
    min_confidence: float = 0.3,
    since_days: int = 0,
) -> str:
    """Search observations and learned patterns with 5-signal ranking.

    Use during Orient step to find relevant past experience. Read-only over
    memory rows (writes retrieval telemetry only; reinforcement happens on
    cos_details, not here — TASK-109).

    Stage-1 metadata pre-filter:
      - `min_confidence` drops decayed/low-trust patterns BEFORE ranking.
        Stale low-signal patterns can otherwise crowd out fresh hits.
        Default 0.3 skips decayed/unvalidated noise (fresh patterns start at
        0.5, so they still pass); pass 0.0 to include everything.
      - `since_days` caps row age. 0 = no cap (default) — age is opt-in so a
        valuable old decision is never silently hidden from default recall.

    Args:
        query: Search text (e.g. "backend rework", "django migration").
        limit: Max results (1-20, default 5).
        memory_type: Filter by type (pattern/workflow/error/decision/discovery). Optional.
        min_confidence: Drop learned_patterns with confidence below this
            value (0.0-1.0). Default 0.3 (skips decayed noise). 0.0 = no filter.
        since_days: Drop rows older than now-`since_days`. 0 = no cap.
            Common: 90 (one quarter) for "recent" queries.

    Returns:
        str: JSON with results list [{id, title, confidence, impact_score, memory_type, source_table}].
    """
    from database import has_fts5_table

    result = memory_search(
        _db_conn,
        query=query,
        limit=limit,
        memory_type=memory_type or None,
        use_fts5=has_fts5_table(_db_conn),
        min_confidence=float(min_confidence),
        since_days=int(since_days) if since_days and since_days > 0 else None,
    )
    # Log each returned row for the outcome-feedback loop.
    rows = (result.get("results") or []) if isinstance(result, dict) else []
    rids = log_retrieval(_db_conn, layer="memory", query=query, rows=rows)
    if isinstance(result, dict):
        result["retrieval_ids"] = rids
    # Router-level telemetry.
    log_router_decision(_db_conn, query=query, chosen_layer="memory", bytes_returned=len(str(rows)))
    # A real Orient memory query — record the marker enforce-memory-check reads,
    # so the honest path is automatic and the marker means an actual search ran.
    _record_memory_check_safe(query)
    return ok(
        result,
        meta={
            "layer": "memory",
            "query": query,
            "source": result.get("source") if isinstance(result, dict) else None,
        },
    )


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
@safe_tool(name="cos_timeline")
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
    return ok(
        result,
        meta={"layer": "memory", "filters_applied": {"domain": domain or None, "days": days}},
    )


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
@safe_tool(name="cos_details")
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
    # Persist the suggestion set so remind-learn-validate.sh
    # can prompt the agent to close the loop after task-done. One line
    # per pattern, format "id<TAB>text" — the hook prints a slice.
    _persist_learn_suggestions_safe(result)
    return ok(
        result,
        meta={
            "layer": "learning",
            "filters_applied": {
                "domain": domain or None,
                "complexity": complexity or None,
                "task_type": task_type or None,
            },
        },
    )


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
