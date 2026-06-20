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
import os
import sys
from pathlib import Path

from database import get_db_stats, get_pooled_conn, init_db
from mcp.server.fastmcp import FastMCP
from tools._shared import apply_module_tool_gating, fail, ok, safe_tool

# ---------------------------------------------------------------------------
# Logging — central via core.logging_os; .mcp.log retained as MCP-specific sink.
# ---------------------------------------------------------------------------
from core.logging_os import setup as _logging_os_setup

_logging_os_setup(level="info")
logger = logging.getLogger("thinking_os")

_LOG_FORMAT = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
try:
    _state_dir = Path(os.environ.get("COS_STATE_DIR") or ".coding-os")
    _state_dir.mkdir(parents=True, exist_ok=True)
    _file_handler = logging.FileHandler(_state_dir / ".mcp.log", mode="a", encoding="utf-8")
    _file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    logging.getLogger().addHandler(_file_handler)
except OSError as _exc:
    logger.debug("mcp log file mirror unavailable: %s", _exc)

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------
mcp = FastMCP("coding_os_mcp")

# ---------------------------------------------------------------------------
# Database bootstrap
# ---------------------------------------------------------------------------
_db_conn = init_db()

# Opt-in continuous indexer. No-op unless COS_BACKGROUND_INDEX=1.
# Wrapped in try/except so a broken indexer never blocks MCP startup.
try:
    from background import maybe_start_indexer

    _bg_status = maybe_start_indexer()
    if _bg_status.get("started"):
        logger.info("background indexer started: %s", _bg_status.get("reason"))
except Exception as exc:
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

    Use this tool to verify the thinking_os database is operational and
    to get a quick summary of stored data volume.

    Returns:
        str: JSON object with keys: tables (row counts), schema_version,
             fts5_available, db_size_bytes, rag (embeddings + doc_chunks status).
    """
    stats = get_db_stats(_db_conn)

    # Surface RAG availability so the agent can decide whether
    # semantic search is wired up before issuing cos_doc_search.
    embeddings_available = False
    try:
        from embeddings import is_available

        embeddings_available = is_available()
    except ImportError as exc:
        logger.debug("Embeddings module unavailable for health check: %s", exc)

    stats["rag"] = {
        "embeddings_available": embeddings_available,
        "embedding_model": "all-MiniLM-L6-v2",
        "embeddings_count": stats["tables"].get("embeddings") or 0,
        "document_chunks_count": stats["tables"].get("document_chunks") or 0,
    }

    # Task store status — lets the agent detect whether
    # `cos_task_*` queries will return data before making the call.
    stats["task_store"] = {
        "tasks_count": stats["tables"].get("tasks") or 0,
    }

    # Background indexer status — surfaced even when the loop
    # is disabled so `cos doctor` can warn about misconfigured state.
    try:
        from background import get_indexer, is_enabled

        stats["background_indexer"] = (
            get_indexer().status()
            if is_enabled()
            else {
                "enabled": False,
                "running": False,
                "reason": "COS_BACKGROUND_INDEX not set",
            }
        )
    except ImportError as exc:  # pragma: no cover — defensive
        logger.debug("background module unavailable: %s", exc)
        stats["background_indexer"] = {
            "enabled": False,
            "running": False,
            "reason": f"import_error: {exc}",
        }

    return ok(stats, meta={"layer": "health"})


# ---------------------------------------------------------------------------
# Import tool modules
# ---------------------------------------------------------------------------
from graph import query_related
from tools.docs import doc_search, list_doc_headers, parse_doc_header
from tools.learning import (
    generate_feedback_drafts,
    learn_extract,
    learn_narrative,
    learn_suggest,
    learn_validate,
)
from tools.logs import log_query
from tools.memory import memory_details, memory_promote, memory_search, memory_timeline
from tools.metrics import metric_query, metric_record, metric_trend
from tools.retrieve import (
    cite_retrievals,
    learn_from_retrievals,
    log_retrieval,
    log_router_decision,
)
from tools.routing import failure_pattern_query, route_model, route_skill
from tools.tasks import task_by_filter, task_dependencies, task_dependents, task_search
from tools.trajectory import trajectory_read, trajectory_snapshot

# ---------------------------------------------------------------------------
# Agent-session resolver — fix for AGENT STREAM "H" label
# ---------------------------------------------------------------------------


def _detect_agent_session_default() -> str | None:
    """Best-effort fallback for MCP tools that accept `agent_session`."""
    import os as _os
    from pathlib import Path as _P

    explicit = (_os.environ.get("COS_AGENT_SESSION_ID") or "").strip()
    if explicit:
        return explicit

    def _first_line(p: "_P") -> str:
        try:
            return p.read_text(encoding="utf-8", errors="ignore").strip() if p.is_file() else ""
        except OSError:
            return ""

    # Priority 0 — the calling panel's own session-id, when a panel dir is
    # in the environment (hook-driven CLI calls). Most accurate signal.
    panel_dir_env = _os.environ.get("COS_PANEL_DIR")
    if panel_dir_env:
        sid = _first_line(_P(panel_dir_env) / "session-id")
        if sid:
            return sid

    # Priority 1 — the agent-level ".active-session" pointer that
    # session-context.sh refreshes every prompt. The long-lived MCP server
    # has no $COS_PANEL_DIR, so this is the freshest signal it can read;
    # the flat "session-id" file is a stale fossil kept only as a last
    # resort (see docs/engineering/state-files.md).
    agent_dir_env = _os.environ.get("COS_AGENT_DIR")
    if agent_dir_env:
        for _fname in (".active-session", "session-id"):
            sid = _first_line(_P(agent_dir_env) / _fname)
            if sid:
                return sid

    # Priority 2 — vendor env markers. Data-driven from
    # adapters/<id>/adapter.yaml::runtime_env_markers (rule #11 — no
    # hardcoded vendor lists in core).
    agent: str | None = None
    if _os.environ.get("COS_AGENT"):
        agent = _os.environ["COS_AGENT"].strip().lower() or None
    else:
        try:
            from board_os._agent_runtime import detect_agent as _detect_agent

            detected = _detect_agent(None)
            # detect_agent returns "agent" or "human" when nothing matches;
            # only treat real adapter ids as a positive identification.
            if detected and detected not in ("human", "agent"):
                agent = detected
        except Exception:
            agent = None
        # Fallback heuristic — CLAUDE_PROJECT_DIR is a weak signal, so it
        # only fires when no stronger signal matched.
        if agent is None and _os.environ.get("CLAUDE_PROJECT_DIR"):
            agent = "claude"

    if agent is None:
        return None

    state_dir = _os.environ.get("COS_STATE_DIR", ".coding-os")
    sid_path = _P(state_dir) / agent / "session-id"
    try:
        if sid_path.is_file():
            raw = sid_path.read_text(encoding="utf-8", errors="ignore").strip()
            if raw:
                return raw
    except OSError:
        pass

    # Last resort — synthesize a per-process id so the column at least
    # carries the agent prefix instead of NULL. The hub's
    # `agentForSession()` substring-matches on "claude" / "codex",
    # so this is enough to render the correct badge.
    return f"ses-{agent}-mcp-{_os.getpid()}"


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


# ---------------------------------------------------------------------------
# Learning tools
# ---------------------------------------------------------------------------
def _persist_learn_suggestions_safe(result: dict) -> None:
    """Append surfaced pattern ids to $COS_AGENT_DIR/.learn-suggestions."""
    try:
        import os as _os
        from pathlib import Path as _P

        agent_dir = _os.environ.get("COS_AGENT_DIR")
        if not agent_dir:
            state_dir = _P(_os.environ.get("COS_STATE_DIR", ".coding-os"))
            agent = _os.environ.get("COS_AGENT", "")
            if not agent:
                marker = state_dir / ".agent"
                if marker.exists():
                    agent = marker.read_text(encoding="utf-8").strip()
            if agent:
                agent_dir = str(state_dir / agent)
        if not agent_dir:
            return
        suggestions = (result or {}).get("suggestions") or []
        if not suggestions:
            return
        target = _P(agent_dir) / ".learn-suggestions"
        target.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        for s in suggestions:
            if not isinstance(s, dict):
                continue
            pid = s.get("id")
            txt = (s.get("pattern") or "").replace("\t", " ").replace("\n", " ")
            if pid is None:
                continue
            lines.append(f"{pid}\t{txt}")
        if lines:
            with target.open("a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
    except Exception as exc:
        logger.debug("_persist_learn_suggestions_safe swallowed: %s", exc)


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
# W7.10 / R4-14: legacy cos_graph stub removed entirely. Use
# cos_graph_resolve(q) → cos_graph_context(uid) / cos_graph_impact(uid)
# / cos_graph_references(uid) instead.


# ---------------------------------------------------------------------------
# Routing tools
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
# Project Trajectory + Failure Archaeology + Routing Drift
# ---------------------------------------------------------------------------


@mcp.tool(
    name="cos_trajectory_snapshot",
    annotations={
        "title": "Project Trajectory Snapshot (Write)",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_trajectory_snapshot(
    session_id: str,
    phase: str = "",
    current_focus: str = "",
    architectural_decisions: str = "[]",
    anti_patterns_discovered: str = "[]",
    open_questions: str = "[]",
    next_logical_step: str = "",
    confidence: float = 0.7,
) -> str:
    """Persist a project trajectory snapshot for the current session.

    Records WHERE the project is heading (phase, focus, architectural decisions,
    anti-patterns discovered, open questions) so future sessions have strategic
    context beyond task history. Each call creates a new row linked to the
    previous snapshot via supersedes_id.

    Args:
        session_id: Current session identifier.
        phase: Current development phase (e.g. "v2 hardening").
        current_focus: What the team is focused on right now.
        architectural_decisions: JSON array of {decision, rationale} objects.
        anti_patterns_discovered: JSON array of {pattern, context} objects.
        open_questions: JSON array of {question, priority} objects or plain strings.
        next_logical_step: Single-sentence description of what comes next.
        confidence: Confidence in this trajectory assessment (0.0-1.0).

    Returns:
        JSON with {status, id, supersedes_id}.
    """
    import json as _json

    try:
        ad = _json.loads(architectural_decisions or "[]")
        apd = _json.loads(anti_patterns_discovered or "[]")
        oq = _json.loads(open_questions or "[]")
    except _json.JSONDecodeError as exc:
        return fail("validation", f"JSON parse error in list field: {exc}")

    result = trajectory_snapshot(
        _db_conn,
        session_id=session_id,
        phase=phase,
        current_focus=current_focus,
        architectural_decisions=ad,
        anti_patterns_discovered=apd,
        open_questions=oq,
        next_logical_step=next_logical_step,
        confidence=confidence,
    )
    return ok(result, meta={"layer": "trajectory"})


@mcp.tool(
    name="cos_trajectory_read",
    annotations={
        "title": "Project Trajectory Read",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_trajectory_read(limit: int = 1) -> str:
    """Return the most recent project trajectory snapshot(s).

    Use at session start to understand WHERE the project is heading before
    looking at the task board. Returns phase, current focus, architectural
    decisions made, anti-patterns discovered, and open questions.

    Args:
        limit: Number of recent snapshots to return (1-20, default 1).

    Returns:
        JSON with {snapshots: [...], count: int}.
    """
    result = trajectory_read(_db_conn, limit=limit)
    return ok(result, meta={"layer": "trajectory"})


@mcp.tool(
    name="cos_failure_pattern_query",
    annotations={
        "title": "Failure Pattern Query",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
@safe_tool
def cos_failure_pattern_query(
    root_cause: str = "",
    domain: str = "",
    limit: int = 10,
) -> str:
    """Aggregate structured failure anatomy from backtrack_events.

    Returns which root_cause categories recur most frequently, with examples.
    Use before planning to avoid known failure modes. Requires migration v25
    (structured backtrack anatomy columns).

    root_cause filter values: wrong_model | scope_too_large | missing_context |
    tool_failure | spec_ambiguity | env_mismatch | other

    Args:
        root_cause: Optional filter to a specific root cause category.
        domain: Reserved for future per-domain filtering.
        limit: Max pattern groups to return (1-50, default 10).

    Returns:
        JSON with {patterns: [{root_cause, count, examples}],
        total_structured, total_backtrack}.
    """
    result = failure_pattern_query(
        _db_conn,
        root_cause=root_cause or None,
        domain=domain or None,
        limit=limit,
    )
    return ok(result, meta={"layer": "routing"})


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
    target = Path(candidate)
    if not target.is_absolute():
        target = (Path.cwd() / target).resolve()
    else:
        try:
            target = target.resolve()
        except OSError as exc:
            return fail("validation", f"cannot resolve path: {exc}")
    # Path-traversal guard. The MCP server is trusted today,
    # but a future external client must never read files outside the
    # project root via this tool.
    project_root = Path.cwd().resolve()
    try:
        target.relative_to(project_root)
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
    root_path = Path(root) if root else Path("docs")
    if not root_path.is_absolute():
        root_path = (Path.cwd() / root_path).resolve()
    else:
        try:
            root_path = root_path.resolve()
        except OSError as exc:
            return fail("validation", f"cannot resolve root: {exc}")
    # Path-traversal guard — root must stay inside project.
    project_root = Path.cwd().resolve()
    try:
        root_path.relative_to(project_root)
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


# ---------------------------------------------------------------------------
# Task store tools
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
    log_router_decision(
        _db_conn, query=query, chosen_layer="tasks", bytes_returned=len(str(results))
    )
    return ok(
        {"results": results, "count": len(results), "retrieval_ids": rids},
        meta={
            "layer": "tasks",
            "query": query,
            "filters_applied": {"status": status or None, "domain": domain or None},
        },
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
    return ok(
        {"task_id": task_id, "dependencies": results, "count": len(results)},
        meta={"layer": "tasks"},
    )


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
    return ok(
        {"task_id": task_id, "dependents": results, "count": len(results)}, meta={"layer": "tasks"}
    )


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
        meta={
            "layer": "tasks",
            "filters_applied": {"status": status or None, "domain": domain or None},
        },
    )


# ---------------------------------------------------------------------------
# Board-OS MCP tools — Scrumban task board
# ---------------------------------------------------------------------------
# Imported from core/board_os/mcp_tools.py. Each tool here is a thin
# @mcp.tool-decorated wrapper that injects the server's shared _db_conn.

try:
    # `from board_os...` requires the project root (parent of `core/`)
    # on sys.path, since `core/` is a namespace package without __init__.py.
    _PROJECT_ROOT = Path(__file__).resolve().parents[2]
    if str(_PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(_PROJECT_ROOT))
    from board_os import mcp_tools as _board_mcp  # type: ignore

    _BOARD_OS_AVAILABLE = True
except ImportError as _exc:
    logger.warning("board_os MCP tools unavailable: %s", _exc)
    _BOARD_OS_AVAILABLE = False


if _BOARD_OS_AVAILABLE:

    @mcp.tool(
        name="cos_task_create",
        annotations={
            "title": "Create New Scrumban Task",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    def cos_task_create(
        title: str,
        swimlane: str,
        kind: str,
        priority: str = "P2",
        appetite: str = "1d",
        epic: str = "",
        labels: list[str] | None = None,
        outcome: str = "",
        acceptance: str = "",
        repro: str = "",
        read_first: list[str] | None = None,
        depends_on: list[str] | None = None,
        status: str = "icebox",
        ready: bool = False,
        agent_session: str = "",
    ) -> str:
        """Create a new Scrumban task file + sync to DB.

        Prefer this over hand-writing YAML. Validates swimlane against
        scrumban-config.yaml and kind against the 8-value enum. Pass
        ready=True to mark the task pullable in one shot; for bug-kind
        tasks pass acceptance= (G/W/T lines) and repro= so the create
        satisfies its own DoR in one call.
        """
        resolved_session = agent_session or _detect_agent_session_default() or None
        return _board_mcp.cos_task_create(
            get_pooled_conn(),
            title=title,
            swimlane=swimlane,
            kind=kind,
            priority=priority,
            appetite=appetite,
            epic=epic or None,
            labels=labels or [],
            outcome=outcome or None,
            acceptance=acceptance or None,
            repro=repro or None,
            read_first=read_first or [],
            depends_on=depends_on or [],
            status=status,
            ready=ready,
            agent_session=resolved_session,
        )

    @mcp.tool(
        name="cos_task_board",
        annotations={
            "title": "Scrumban Board State",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_task_board(
        swimlane: str = "",
        kind: str = "",
        epic: str = "",
        status_filter: list[str] | None = None,
        include_archive: bool = False,
        limit: int = 50,
        page_size: int = 50,
        cursor: str = "",
    ) -> str:
        """Return the board state grouped by (swimlane, status) with WIP info. Complete/archive columns are keyset-paginated (pass cursor + status_filter to load more)."""
        return _board_mcp.cos_task_board(
            get_pooled_conn(),
            swimlane=swimlane or None,
            kind=kind or None,
            epic=epic or None,
            status_filter=status_filter,
            include_archive=include_archive,
            limit=limit,
            page_size=page_size,
            cursor=cursor or None,
        )

    @mcp.tool(
        name="cos_task_show",
        annotations={
            "title": "Show Single Task (frontmatter + body)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_task_show(task_id: str, include_body: bool = True) -> str:
        """Show a single task's frontmatter fields and full markdown body — in-session alternative to raw ls/grep/Read on docs/tasks."""
        return _board_mcp.cos_task_show(
            get_pooled_conn(),
            task_id=task_id,
            include_body=include_body,
        )

    @mcp.tool(
        name="cos_task_history",
        annotations={
            "title": "Task History (create + transitions + edits + commits)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_task_history(task_id: str, include_commits: bool = True, limit: int = 200) -> str:
        """Full actor-attributed task history — creation, status transitions, field edits, and git commits."""
        return _board_mcp.cos_task_history(
            get_pooled_conn(),
            task_id=task_id,
            include_commits=include_commits,
            limit=limit,
        )

    @mcp.tool(
        name="cos_task_edit",
        annotations={
            "title": "Edit Task Fields / Body (actor-attributed)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    def cos_task_edit(
        task_id: str,
        title: str = "",
        priority: str = "",
        swimlane: str = "",
        appetite: str = "",
        epic: str = "",
        labels_csv: str = "",
        body: str = "",
        actor_type: str = "agent",
        actor_id: str = "",
        source: str = "mcp",
    ) -> str:
        """Edit a task's frontmatter fields and/or body; each change is recorded to the actor-attributed edit history."""
        return _board_mcp.cos_task_edit(
            get_pooled_conn(),
            task_id=task_id,
            title=title or None,
            priority=priority or None,
            swimlane=swimlane or None,
            appetite=appetite or None,
            epic=epic or None,
            labels=[s.strip() for s in labels_csv.split(",") if s.strip()] if labels_csv else None,
            body=body or None,
            actor_type=actor_type,
            actor_id=actor_id or None,
            source=source,
        )

    @mcp.tool(
        name="cos_task_link",
        annotations={
            "title": "Link a Task to a Forge Issue/PR (external_ref)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_task_link(task_id: str, ref: str) -> str:
        """Set a task's optional external_ref (e.g. github#42) — forge auto-detected; metadata only, never the id."""
        return _board_mcp.cos_task_link(get_pooled_conn(), task_id=task_id, ref=ref)

    @mcp.tool(
        name="cos_presence_query",
        annotations={
            "title": "Live Agent Presence (sessions + states)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_presence_query(agent: str = "") -> str:
        """Return per-agent presence state and live-session inventory.

        Reads `.coding-os/<agent>/sessions/*.json` (the same files
        agent-presence.sh writes) and applies the SSOT rules in
        `board_os.presence`.  When `agent` is empty, every adapter
        registered in adapters/<id>/adapter.yaml is reported.

        Used by `cos daily`, CI gates, and the live-agents board UI to
        verify zombie sessions are gone after deploy.
        """
        try:
            from board_os.hub_adapter_manifest import list_agent_manifest_rows
            from board_os.presence import (
                agent_state as _agent_state_q,
                session_inventory as _session_inventory_q,
            )
        except ImportError as exc:
            return fail(
                "unavailable",
                f"board_os presence module not importable: {exc}",
                retryable=False,
            )

        # Resolve the project root the same way the web routes do so
        # multi-project servers inspect the right .coding-os/ tree.
        try:
            from web._project_context import current_project_root  # type: ignore

            root = current_project_root()
        except Exception as exc:
            return fail(
                "unavailable",
                f"cannot resolve project root: {exc}",
                retryable=False,
            )

        agents = (
            [agent.strip()]
            if agent.strip()
            else [str(r.get("id") or "") for r in list_agent_manifest_rows() if r.get("id")]
        )
        states: dict[str, str] = {}
        sessions: list[dict] = []
        for aid in agents:
            if not aid:
                continue
            d = root / ".coding-os" / aid / "sessions"
            states[aid] = _agent_state_q(d)
            sessions.extend(_session_inventory_q(aid, d))
        return ok(
            {
                "agent_states": states,
                "session_states": sessions,
                "session_counts": {
                    aid: sum(1 for s in sessions if s["agent"] == aid) for aid in agents
                },
                "scope": "per_project",
                "root": str(root),
            }
        )

    @mcp.tool(
        name="cos_task_move",
        annotations={
            "title": "Move Task to New Status",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    def cos_task_move(
        task_id: str,
        to: str,
        reason: str = "",
        bypass_wip: bool = False,
        agent_session: str = "",
    ) -> str:
        """Transition a task through the Scrumban state machine."""
        resolved_session = agent_session or _detect_agent_session_default() or None
        return _board_mcp.cos_task_move(
            get_pooled_conn(),
            task_id=task_id,
            to=to,
            reason=reason or None,
            bypass_wip=bypass_wip,
            agent_session=resolved_session,
        )

    @mcp.tool(
        name="cos_task_reposition",
        annotations={
            "title": "Reposition Task (status and/or swimlane)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    def cos_task_reposition(
        task_id: str,
        swimlane: str = "",
        to: str = "",
        reason: str = "",
        bypass_wip: bool = False,
        agent_session: str = "",
    ) -> str:
        """Update Scrumban status and/or swimlane (MD frontmatter + sync)."""
        resolved_session = agent_session or _detect_agent_session_default() or None
        return _board_mcp.cos_task_reposition(
            get_pooled_conn(),
            task_id=task_id,
            swimlane=swimlane or None,
            to=to or None,
            reason=reason or None,
            bypass_wip=bypass_wip,
            agent_session=resolved_session,
        )

    @mcp.tool(
        name="cos_task_ready",
        annotations={
            "title": "Mark Task Ready (toggle pull-gate label)",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_task_ready(
        task_id: str,
        ready: bool = True,
        agent_session: str = "",
    ) -> str:
        """Add or remove the 'ready' label that gates icebox→in_progress."""
        resolved_session = agent_session or _detect_agent_session_default() or None
        return _board_mcp.cos_task_ready(
            get_pooled_conn(),
            task_id=task_id,
            ready=ready,
            agent_session=resolved_session,
        )

    @mcp.tool(
        name="cos_task_reclaim",
        annotations={
            "title": "Reclaim Zombie in_progress Tasks",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_task_reclaim(
        idle_hours: int = 0,
        dry_run: bool = False,
        agent_session: str = "",
    ) -> str:
        """Reclaim zombie in_progress tasks (idle + owner session inactive) to icebox+ready."""
        resolved_session = agent_session or _detect_agent_session_default() or None
        return _board_mcp.cos_task_reclaim(
            get_pooled_conn(),
            idle_hours=idle_hours or None,
            dry_run=dry_run,
            agent_session=resolved_session,
        )

    @mcp.tool(
        name="cos_task_reconcile",
        annotations={
            "title": "Reconcile Stranded Tasks (review-first)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_task_reconcile(include_active: bool = False) -> str:
        """Triage stranded in_progress/testing tasks with completion evidence + a review recommendation (read-only)."""
        return _board_mcp.cos_task_reconcile(get_pooled_conn(), include_active=include_active)

    @mcp.tool(
        name="cos_task_pick",
        annotations={
            "title": "Pick Next Task to Work On",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_task_pick(
        swimlane: str = "",
        priority_min: str = "P2",
        max_candidates: int = 5,
    ) -> str:
        """Return top candidate tasks to start next, ranked by priority."""
        return _board_mcp.cos_task_pick(
            get_pooled_conn(),
            swimlane=swimlane or None,
            priority_min=priority_min,
            max_candidates=max_candidates,
        )

    @mcp.tool(
        name="cos_task_claim_next",
        annotations={
            "title": "Atomically Claim Next Runnable Task",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    def cos_task_claim_next(
        swimlane: str = "",
        priority_min: str = "P2",
        agent_session: str = "",
    ) -> str:
        """Atomically select+claim the top runnable task for this session (or claimed=null)."""
        return _board_mcp.cos_task_claim_next(
            get_pooled_conn(),
            swimlane=swimlane or None,
            priority_min=priority_min,
            agent_session=agent_session or None,
        )

    @mcp.tool(
        name="cos_task_daily",
        annotations={
            "title": "Daily Standup Summary",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_task_daily(since: str = "24h", agent_session: str = "") -> str:
        """Produce the daily standup summary."""
        return _board_mcp.cos_task_daily(
            get_pooled_conn(),
            since=since,
            agent_session=agent_session or None,
        )

    @mcp.tool(
        name="cos_task_retro",
        annotations={
            "title": "Weekly Retrospective",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_task_retro(since: str = "7d") -> str:
        """Weekly retro metrics (cycle time, throughput, emergency count)."""
        return _board_mcp.cos_task_retro(get_pooled_conn(), since=since)

    @mcp.tool(
        name="cos_task_wip_check",
        annotations={
            "title": "WIP Cap Health Check",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    def cos_task_wip_check() -> str:
        """Lightweight check of current WIP counts vs. configured caps."""
        return _board_mcp.cos_task_wip_check(get_pooled_conn())

    @mcp.tool(
        name="cos_work_log_append",
        annotations={
            "title": "Append Line to Task Work Log",
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
            "openWorldHint": False,
        },
    )
    def cos_work_log_append(
        task_id: str,
        summary: str,
        agent_session: str = "",
        source: str = "manual",
    ) -> str:
        """Append one Work Log line to a task. Critical for Codex sessions."""
        resolved_session = agent_session or _detect_agent_session_default() or None
        return _board_mcp.cos_work_log_append(
            get_pooled_conn(),
            task_id=task_id,
            summary=summary,
            agent_session=resolved_session,
            source=source,
        )


# ---------------------------------------------------------------------------
# Retrieval feedback
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
    result = learn_from_retrievals(
        _db_conn, lookback_days=int(lookback_days), dry_run=bool(dry_run)
    )
    return ok(result, meta={"layer": "learning"})


# ---------------------------------------------------------------------------
# Agent digest
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

    root = Path(project_root) if project_root else Path(os.environ.get("COS_PROJECT_ROOT", "."))
    result = regenerate(_db_conn, project_root=root)
    return ok(result, meta={"layer": "learning"})


# ---------------------------------------------------------------------------
# Retrieval quality / enrichment gate
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
        _db_conn,
        lookback_days=int(lookback_days),
        layer=layer or None,
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
# 9 formula-agent supervisor tools.
# 3 role-based routing tools (cos_analyze_task, cos_compose_chain,
#           cos_role_info).
# 2 dispatch tools.
# ---------------------------------------------------------------------------
try:
    from database import DEFAULT_DB_PATH as _DEFAULT_DB_PATH
    from tools.cognition import register_all as _register_cognition_tools

    _register_cognition_tools(mcp, str(_DEFAULT_DB_PATH))
    logger.info("Cognition tools registered (9 supervisor + 3 routing + 2 dispatch = 14 tools)")
except Exception as _cog_exc:  # pragma: no cover
    logger.warning("cognition tools unavailable: %s", _cog_exc)


# ---------------------------------------------------------------------------
# 17 cos_graph_* MCP tools (knowledge-graph layer).
#
# The implementations live in `core/graph_os/tools/graph.py`; the wrappers
# here expose them via FastMCP with MCP-friendly parameter types (comma-
# separated strings instead of Sequence[str], etc.). Every wrapper stays
# envelope-compliant because the underlying functions already route
# through ok()/fail().
# ---------------------------------------------------------------------------
try:
    from graph_os.tools import (
        graph as _graph_tools,
    )

    _GRAPH_TOOLS_AVAILABLE = True
except ImportError as _graph_import_exc:  # pragma: no cover — defensive
    logger.warning("graph_os tools unavailable: %s", _graph_import_exc)
    _graph_tools = None  # type: ignore[assignment]
    _GRAPH_TOOLS_AVAILABLE = False


def _csv(value: str) -> list[str] | None:
    """Parse a comma-separated CLI-style string into a clean list or None."""
    if not value:
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return parts or None


def _graph_unavailable() -> str:
    """Envelope the agent sees when graph_os tools can't be imported.

    B20: MCP tool returns must be JSON-encoded strings. ``fail()`` from
    ``tools._shared`` already returns ``json.dumps(...)`` so this
    function always returns a ``str``. The explicit ``json.dumps`` wrapper
    below makes the contract unambiguous should the import path change.
    """
    import json as _json

    return _json.dumps(
        {
            "ok": False,
            "error": {
                "category": "unavailable",
                "retryable": False,
                "message": "graph_os package not importable; install graph_os extra",
            },
        }
    )


if _GRAPH_TOOLS_AVAILABLE:

    @mcp.tool(
        name="cos_graph_query",
        annotations={
            "title": "Graph Hybrid Search",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_query_tool(
        q: str,
        kinds: str = "",
        limit: int = 10,
        max_hops: int = 2,
        confidence_min: float = 0.3,
        include_spine: bool = False,
    ) -> str:
        """Hybrid search over node labels + docstrings (lexical + graph expansion).

        TIP: prefer SHORT terms ("sdk_dispatcher", "ClaudeSDKDispatcher.dispatch") or
        a literal path / uid. Long natural-language queries return weaker matches
        because the index is built from labels + docstrings, not free text.

        UID scheme (also accepted as `q`):
          code:file:<path> · code:function:<path>::<name> · code:class:<path>::<name>
          code:method:<path>::<class>.<name> · code:module:<dotted>
          doc:file:<path> · doc:heading:<path>#<slug>:<level> · folder:<path>

        When the query looks like a path or uid and the lexical pass
        returns nothing, the tool falls back to a direct uid lookup so
        the agent gets a single-item hit instead of empty results.

        Args:
            q: Short term, path, or uid (non-empty). NL queries work but degrade.
            kinds: Comma-separated filter of node kinds (e.g. "function,class,method"). Empty = all.
            limit: Max results (default 10).
            max_hops: Walk expansion depth (default 2).
            confidence_min: Edge confidence floor (default 0.3).
            include_spine: S3 — attach the CONTAINS-ancestor chain to each result for breadcrumbs.

        Returns:
            JSON envelope with `results` array. See docs/engineering/graph_os-queries.md.
        """
        return _graph_tools.cos_graph_query(
            q,
            kinds=_csv(kinds),
            limit=int(limit),
            max_hops=int(max_hops),
            confidence_min=float(confidence_min),
            include_spine=bool(include_spine),
        )

    @mcp.tool(
        name="cos_graph_context",
        annotations={
            "title": "Graph Neighbourhood",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_context_tool(
        uid_or_name: str,
        direction: str = "both",
        depth: int = 1,
        include_content: bool = False,
        include_evidence: bool = False,
        include_spine: bool = False,
    ) -> str:
        """Return callers + callees + siblings + referenced docs around a symbol.

        Args:
            uid_or_name: Node uid or fuzzy label. Uid scheme:
                ``code:file:<path>`` | ``code:function:<path>::<name>`` |
                ``code:class:<path>::<name>`` | ``code:module:<dotted>`` |
                ``doc:file:<path>`` | ``doc:heading:<path>#<slug>:<level>`` |
                ``folder:<path>``. Raw repo paths (``core/foo.py``) are
                auto-resolved to ``code:file:`` / ``doc:file:`` / ``folder:``;
                if all variants miss, a fuzzy label match is tried. Run
                ``cos_graph_query`` first to discover candidates.
            direction: "in" | "out" | "both".
            depth: BFS depth (default 1).
            include_content: When True, each returned node gains a ``content``
                field with source text read from ``file_path:start_line..end_line``
                (capped at 2000 chars, with ``truncated: bool``). Silently skipped
                when the file is missing or the node has no file_path. (B21)
            include_evidence: JOIN evidence rows (costs ~2× tokens).
            include_spine: S3 — pulls the CONTAINS-ancestor chain (file → folder → …)
                so the UI can render breadcrumbs.
        """
        return _graph_tools.cos_graph_context(
            uid_or_name,
            direction=str(direction),
            depth=int(depth),
            include_content=bool(include_content),
            include_evidence=bool(include_evidence),
            include_spine=bool(include_spine),
        )

    @mcp.tool(
        name="cos_graph_impact",
        annotations={
            "title": "Graph Blast-Radius",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_impact_tool(
        uid: str,
        direction: str = "downstream",
        depth: int = 3,
        confidence_min: float = 0.5,
    ) -> str:
        """Group affected nodes by risk tier (will_break / should_review / context).

        Args:
            uid: Fully-qualified node uid. Scheme: ``code:file:<path>`` |
                ``code:function:<path>::<name>`` | ``code:class:<path>::<name>`` |
                ``code:module:<dotted>`` | ``doc:file:<path>`` | ``folder:<path>``.
                Raw repo paths (``core/foo.py``) are auto-resolved to
                ``code:file:`` / ``doc:file:`` / ``folder:``. If unsure, run
                ``cos_graph_query`` first to discover the right uid.
            direction: "downstream" (callers — break if `uid` changes) |
                "upstream" (deps `uid` calls/imports) | "both".
            depth: BFS hop limit (default 3).
            confidence_min: Drop edges below this score (default 0.5).
        """
        return _graph_tools.cos_graph_impact(
            uid,
            direction=str(direction),
            depth=int(depth),
            confidence_min=float(confidence_min),
        )

    @mcp.tool(
        name="cos_graph_detect_changes",
        annotations={
            "title": "Graph Pre-Commit Self-Review",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_detect_changes_tool(
        files: str = "",
        scope: str = "working",
        analyze_downstream: bool = True,
    ) -> str:
        """Map changed files to affected symbols + downstream tasks + risk level.

        Args:
            files: Comma-separated file paths (empty → echo empty envelope).
            scope: Label only; "working" | "staged" | "HEAD~1..HEAD".
            analyze_downstream: Walk transitive blast radius.
        """
        return _graph_tools.cos_graph_detect_changes(
            scope=str(scope),
            files=_csv(files),
            analyze_downstream=bool(analyze_downstream),
        )

    @mcp.tool(
        name="cos_graph_trace",
        annotations={
            "title": "Graph Execution Trace",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_trace_tool(
        entry_uid: str,
        terminals: str = "return,exception",
        max_steps: int = 50,
        include_external: bool = False,
    ) -> str:
        """Forward execution walk from `entry_uid` until terminals.

        Args:
            entry_uid: Function/method uid to start from, e.g.
                ``code:function:core/foo.py::bar``. Raw paths or names are
                auto-resolved (file → ``code:file:`` then entry-point heuristic).
                Run ``cos_graph_query`` first if unsure.
            terminals: Comma-separated edge labels that stop the walk.
            max_steps: Hard cap on emitted steps.
        """
        return _graph_tools.cos_graph_trace(
            entry_uid,
            terminals=tuple(_csv(terminals) or ("return", "exception")),
            max_steps=int(max_steps),
            include_external=bool(include_external),
        )

    @mcp.tool(
        name="cos_graph_similar",
        annotations={
            "title": "Graph Semantic Similarity",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_similar_tool(
        uid: str,
        top_k: int = 5,
        confidence_min: float = 0.5,
    ) -> str:
        """Return the top-K nodes most similar to `uid` (difflib baseline).

        Args:
            uid: Fully-qualified node uid (see ``cos_graph_impact`` for
                scheme). Raw repo paths are auto-resolved to
                ``code:file:`` / ``doc:file:`` / ``folder:``.
            top_k: Number of similar nodes to return.
            confidence_min: Minimum similarity score (0.0–1.0).
        """
        return _graph_tools.cos_graph_similar(
            uid,
            top_k=int(top_k),
            confidence_min=float(confidence_min),
        )

    @mcp.tool(
        name="cos_graph_search",
        annotations={
            "title": "Graph Hybrid Semantic Search",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_search_tool(
        query: str,
        top_k: int = 10,
    ) -> str:
        """Find code symbols by free text — hybrid semantic + lexical + centrality.

        Args:
            query: Natural-language or code-ish query (e.g. "validate jwt token").
            top_k: Number of results to return (1–50).
        """
        return _graph_tools.cos_graph_search(query, top_k=int(top_k))

    @mcp.tool(
        name="cos_graph_references",
        annotations={
            "title": "Graph Inbound References",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_references_tool(
        uid: str,
        kinds: str = "",
        limit: int = 100,
    ) -> str:
        """List inbound edges — "who references this?".

        Args:
            uid: Fully-qualified node uid. Scheme: ``code:file:<path>`` |
                ``code:function:<path>::<name>`` | ``code:class:<path>::<name>`` |
                ``code:module:<dotted>`` | ``doc:file:<path>`` | ``folder:<path>``.
                Raw repo paths are auto-resolved.
            kinds: Comma-separated edge types. Empty string (default)
                picks edge types automatically per node-kind — class
                nodes get ``constructs+has_param_type+is_decorated_by+inherits_from``,
                function/method get ``calls+accesses_field+imports``, files
                get ``imports+links_to+references_doc+contains``. R4-02.
            limit: Max edges returned (default 100).
        """
        parsed = tuple(_csv(kinds) or ())
        return _graph_tools.cos_graph_references(
            uid,
            kinds=parsed if parsed else None,
            limit=int(limit),
        )

    @mcp.tool(
        name="cos_graph_path",
        annotations={
            "title": "Graph Shortest Path",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_path_tool(
        source_uid: str,
        target_uid: str,
        max_hops: int = 5,
    ) -> str:
        """Shortest path between two nodes (either direction).

        Args:
            source_uid: Origin uid (auto-resolves raw paths; see
                ``cos_graph_impact`` for the scheme).
            target_uid: Destination uid (same rules as ``source_uid``).
            max_hops: BFS depth limit (default 5).
        """
        return _graph_tools.cos_graph_path(
            source_uid,
            target_uid,
            max_hops=int(max_hops),
        )

    @mcp.tool(
        name="cos_graph_export",
        annotations={
            "title": "Graph Subgraph Export",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_export_tool(
        format: str = "json",
        root_uid: str = "",
        edge_types: str = "",
        max_nodes: int = 500,
        include_spine: bool = False,
        mode: str = "auto",
        exclude_kinds: str = "__default__",
    ) -> str:
        """Export a subgraph as json | mermaid | dot.

        Args:
            format: Output format (``json`` / ``mermaid`` / ``dot``).
            root_uid: Optional seed; empty walks the edge table.
            edge_types: Comma-separated edge filter (empty = all).
            max_nodes: Hard cap on node count.
            include_spine: S3 — also include the CONTAINS ancestor chain.
            mode: TASK-141 view-mode blend when no root is pinned —
                ``auto`` (semantic + contains, default), ``containment``,
                ``dependencies``, or ``processes``.
            exclude_kinds: Comma-separated noise kinds to drop. Sentinel
                ``__default__`` (default) applies the built-in noise list;
                empty string disables filtering.
        """
        if exclude_kinds == "__default__":
            ek = None
        elif exclude_kinds == "":
            ek = []
        else:
            ek = list(_csv(exclude_kinds) or ())
        return _graph_tools.cos_graph_export(
            format=str(format),
            root_uid=root_uid or None,
            edge_types=_csv(edge_types),
            max_nodes=int(max_nodes),
            include_spine=bool(include_spine),
            mode=str(mode),
            exclude_kinds=ek,
        )

    @mcp.tool(
        name="cos_graph_rename_plan",
        annotations={
            "title": "Graph Rename Plan",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_rename_plan_tool(
        uid: str,
        new_name: str,
        check_strings: bool = True,
    ) -> str:
        """Plan a rename — call-sites, docs, tests, strings, risk.

        Args:
            uid: Symbol to rename. Scheme: ``code:function:<path>::<name>`` |
                ``code:class:<path>::<name>`` | ``code:module:<dotted>``.
                Raw paths are auto-resolved when applicable.
            new_name: Replacement symbol name.
            check_strings: Also scan string literals for the old name.
        """
        return _graph_tools.cos_graph_rename_plan(
            uid,
            new_name,
            check_strings=bool(check_strings),
        )

    @mcp.tool(
        name="cos_graph_contracts",
        annotations={
            "title": "Graph API Contracts",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_contracts_tool(
        scope: str = "all",
        kinds: str = "http,mcp,grpc,event,websocket",
        include_test_sources: bool = False,
    ) -> str:
        """Enumerate every handler declared in the graph (HTTP / MCP / gRPC / events / WS)."""
        return _graph_tools.cos_graph_contracts(
            scope=str(scope),
            kinds=tuple(_csv(kinds) or ("http", "mcp", "grpc", "event", "websocket")),
            include_test_sources=bool(include_test_sources),
        )

    @mcp.tool(
        name="cos_graph_entrypoints",
        annotations={
            "title": "Graph Entry Points (Scored)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_entrypoints_tool(
        top: int = 20,
        kind: str = "",
        min_score: float = 0.05,
        diversify: bool = True,
    ) -> str:
        """Top-N scored entry points (main / cli / http / cron / test) — TASK-081."""
        return _graph_tools.cos_graph_entrypoints(
            top=int(top),
            kind=(kind or None),
            min_score=float(min_score),
            diversify=bool(diversify),
        )

    @mcp.tool(
        name="cos_graph_communities",
        annotations={
            "title": "Graph Communities / Processes (Louvain)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_communities_tool(
        top: int = 50,
        min_size: int = 2,
        max_members: int = 10,
    ) -> str:
        """Louvain process clusters — response key is `processes` (not `communities`)."""
        return _graph_tools.cos_graph_communities(
            top=int(top),
            min_size=int(min_size),
            max_members=int(max_members),
        )

    @mcp.tool(
        name="cos_graph_resolve",
        annotations={
            "title": "Graph UID Resolver (NL → canonical uid)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_resolve_tool(
        q: str,
        kinds: str = "",
        top: int = 10,
    ) -> str:
        """Resolve a natural-language label, path, or partial uid to canonical uids.

        Use this BEFORE other cos_graph_* tools when you don't know the exact uid.
        Tries: direct uid → path/qualname → FTS5 full-text → LIKE fallback.

        UID scheme:
          code:file:<path> · code:function:<path>::<name> · code:class:<path>::<name>
          code:method:<path>::<class>.<name> · code:module:<dotted>
          doc:file:<path> · doc:heading:<path>#<slug>:<level> · folder:<path>

        Args:
            q: Natural language ("the dispatcher function"), label ("ClaudeSDKDispatcher"),
               path ("adapters/claude/sdk_dispatcher.py"), or qualname ("Class.method").
            kinds: Comma-separated kind filter (e.g. "function,method,class"). Empty = all.
            top: Max results (default 10).

        Returns:
            JSON envelope with `results` (ranked list of {uid, kind, label, …}) and
            `strategy` (which resolution path matched).
        """
        return _graph_tools.cos_graph_resolve(
            q,
            kinds=_csv(kinds) or None,
            top=int(top),
        )

    @mcp.tool(
        name="cos_graph_centrality",
        annotations={
            "title": "Graph Centrality (degree / betweenness)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_centrality_tool(
        metric: str = "degree",
        top: int = 20,
        kind: str = "",
    ) -> str:
        """Hub detection — surface high-degree (or high-betweenness) nodes.

        Use to identify chokepoints / refactor priorities / nodes that demand
        extra review.

        Args:
            metric: "degree" (cheap, default) or "betweenness" (expensive).
            top: Max nodes returned (default 20).
            kind: Optional kind filter (e.g. "function", "class"). Empty = all.

        Returns:
            JSON envelope with `nodes` ranked by centrality score.
        """
        return _graph_tools.cos_graph_centrality(
            metric=metric,
            top=int(top),
            kind=kind or None,
        )

    @mcp.tool(
        name="cos_graph_ranking",
        annotations={
            "title": "Graph PageRank (importance / personalised)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_ranking_tool(
        query: str = "",
        top: int = 20,
        kind: str = "",
        damping: float = 0.85,
        iterations: int = 30,
    ) -> str:
        """PageRank — node importance, optionally personalised by query.

        Use for: knowledge condensation (top-N canonical concepts),
        query-personalised search ranking, documentation sourcing.

        Args:
            query: Optional personalisation query ("auth", "graph backend").
                   Empty = global PageRank.
            top: Max nodes returned (default 20).
            kind: Optional kind filter. Empty = all.
            damping: PageRank damping factor (default 0.85).
            iterations: Power-iteration count (default 30).

        Returns:
            JSON envelope with `nodes` ranked by PageRank score.
        """
        return _graph_tools.cos_graph_ranking(
            query=query or None,
            top=int(top),
            kind=kind or None,
            damping=float(damping),
            iterations=int(iterations),
        )

    @mcp.tool(
        name="cos_graph_cycles",
        annotations={
            "title": "Graph Circular Dependencies (SCC)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_cycles_tool(
        scope: str = "imports",
        top: int = 20,
        min_size: int = 2,
    ) -> str:
        """Detect circular dependencies as strongly-connected components.

        Args:
            scope: "imports" (module-level circular deps, the design smell) or
                "calls" (function cycles incl. legitimate mutual recursion).
            top: Max cycles returned (default 20).
            min_size: Minimum SCC size to report (default 2).

        Returns:
            JSON envelope with `cycles` (each {size, members}) + total_count.
        """
        return _graph_tools.cos_graph_cycles(
            scope=str(scope),
            top=int(top),
            min_size=int(min_size),
        )

    @mcp.tool(
        name="cos_graph_dead_code",
        annotations={
            "title": "Graph Dead-Code Candidates",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_dead_code_tool(
        kind: str = "",
        top: int = 50,
        include_tests: bool = False,
    ) -> str:
        """List in-repo symbols with zero non-test inbound references (dead-code candidates).

        Surfaces functions / methods / classes that nothing (outside tests)
        calls, constructs, subclasses, or type-references — the inverse of
        centrality. Candidates only: dynamic-dispatch / CLI-registered /
        externally-called symbols may appear; verify with cos_graph_references
        before deleting.

        Args:
            kind: Optional filter — function | method | class. Empty = all three.
            top: Max candidates returned (default 50, max 500).
            include_tests: Count test-sourced edges + include test files (default False).

        Returns:
            JSON envelope with `dead` (list) + `total_count`.
        """
        return _graph_tools.cos_graph_dead_code(
            kind=kind or "",
            top=int(top),
            include_tests=bool(include_tests),
        )

    @mcp.tool(
        name="cos_graph_test_gap",
        annotations={
            "title": "Graph Test-Gap (untested symbols)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_test_gap_tool(
        kind: str = "",
        top: int = 50,
    ) -> str:
        """List prod function/method/class with zero inbound edge from any test (untested symbols).

        Candidates only: indirect exercise (CLI / fixtures / dynamic dispatch)
        may not appear as a graph edge. Shell excluded (no call-graph).

        Args:
            kind: Optional filter — function | method | class. Empty = all three.
            top: Max returned (default 50, max 500).

        Returns:
            JSON envelope with `untested` (list) + total_count.
        """
        return _graph_tools.cos_graph_test_gap(kind=kind or "", top=int(top))

    @mcp.tool(
        name="cos_graph_diff",
        annotations={
            "title": "Graph Diff (git revision blast-radius)",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_diff_tool(
        base: str = "HEAD~1",
        head: str = "HEAD",
        analyze_downstream: bool = True,
    ) -> str:
        """Graph blast-radius of a git revision range (base..head).

        Resolves changed files via `git diff --name-only base..head`, then maps
        them to affected symbols + downstream consumers + risk (PR/review view).

        Args:
            base: Base git revision (default HEAD~1).
            head: Head git revision (default HEAD).
            analyze_downstream: Walk transitive consumers (default True).

        Returns:
            JSON envelope with range, files, symbols, downstream_consumers, risk_level.
        """
        return _graph_tools.cos_graph_diff(
            base=str(base),
            head=str(head),
            analyze_downstream=bool(analyze_downstream),
        )

    @mcp.tool(
        name="cos_graph_doctor",
        annotations={
            "title": "Graph Health Doctor",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        },
    )
    @safe_tool
    def cos_graph_doctor_tool(
        fix: bool = False,
    ) -> str:
        """Graph health snapshot — orphans, dangling edges, duplicates, backend status.

        Call when graph queries return nothing or `meta.backend_fallback=true`.

        Args:
            fix: If True, attempt safe repairs (delete dangling edges). Default False
                 — use the report-only mode to see what would change first.

        Returns:
            JSON envelope with `healthy` boolean, `issues` list, `stats` dict.
        """
        return _graph_tools.cos_graph_doctor(
            fix=bool(fix),
        )

else:
    # Deterministic unavailable responses so agents still see a valid envelope.
    for _name in (
        "cos_graph_query",
        "cos_graph_resolve",
        "cos_graph_context",
        "cos_graph_impact",
        "cos_graph_detect_changes",
        "cos_graph_trace",
        "cos_graph_similar",
        "cos_graph_search",
        "cos_graph_references",
        "cos_graph_path",
        "cos_graph_export",
        "cos_graph_rename_plan",
        "cos_graph_contracts",
        "cos_graph_entrypoints",
        "cos_graph_communities",
        "cos_graph_centrality",
        "cos_graph_ranking",
        "cos_graph_doctor",
    ):

        def _make_stub(tool_name: str):
            @mcp.tool(
                name=tool_name,
                annotations={"title": f"{tool_name} (unavailable)", "readOnlyHint": True},
            )
            @safe_tool
            def _stub(*_args: object, **_kwargs: object) -> str:
                return _graph_unavailable()

            return _stub

        _make_stub(_name)


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
            "task_outcomes",
            "agent_metrics",
            "learned_patterns",
            "observations",
            "session_summaries",
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
        logger.info("Starting thinking_os MCP server (stdio)...")
        gating = apply_module_tool_gating(mcp)
        if gating["removed"]:
            logger.info(
                "Module gating: removed %d tool(s) for disabled module(s) %s",
                len(gating["removed"]),
                gating["disabled_modules"],
            )
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
