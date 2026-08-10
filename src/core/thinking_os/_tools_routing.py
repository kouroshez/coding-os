"""Routing, trajectory, and retrieval-feedback cos_* tools."""

from __future__ import annotations

from _server_runtime import _db_conn, logger, mcp
from tools._shared import fail, ok, safe_tool
from tools.retrieve import cite_retrievals, learn_from_retrievals
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
        raise ValueError("retrieval_ids must be comma-separated integers") from None
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
    logger.info("Cognition tools registered")
except Exception as _cog_exc:  # pragma: no cover
    logger.warning("cognition tools unavailable: %s", _cog_exc)
