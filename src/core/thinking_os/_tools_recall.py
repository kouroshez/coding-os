"""Memory recall and promotion cos_* tools registered on the shared server."""

from __future__ import annotations

from _server_runtime import (
    _db_conn,
    _record_memory_check_safe,
    mcp,
)
from tools._shared import fail, ok, safe_tool
from tools.memory import memory_details, memory_promote, memory_search, memory_timeline
from tools.retrieve import log_retrieval, log_router_decision


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
    memory rows: retrieval telemetry only. Neither this tool nor cos_details
    moves confidence — only cos_learn_validate does.

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
