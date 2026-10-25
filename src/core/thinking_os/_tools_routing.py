"""Routing, trajectory, and retrieval-feedback cos_* tools."""

from __future__ import annotations

from _server_runtime import _db_conn, logger, mcp
from tools._shared import fail, ok, safe_tool
from tools.routing import failure_pattern_query, route_model_bandit, route_skill
from tools.trajectory import trajectory_read, trajectory_snapshot

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
    result = route_model_bandit(
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
# 9 formula-agent supervisor tools.
# 3 role-based routing tools (cos_analyze_task, cos_compose_chain,
#           cos_role_info).
# 2 dispatch tools.
# ---------------------------------------------------------------------------
try:
    from database import DEFAULT_DB_PATH as _DEFAULT_DB_PATH
    from tools.cognition import register_all as _register_cognition_tools

    _register_cognition_tools(mcp, str(_DEFAULT_DB_PATH))
    logger.info("Cognition tools registered")
except Exception as _cog_exc:  # pragma: no cover
    logger.warning("cognition tools unavailable: %s", _cog_exc)
