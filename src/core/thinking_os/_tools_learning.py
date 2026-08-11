"""Learning-loop cos_* tools registered on the shared server."""

from __future__ import annotations

from _server_runtime import (
    _db_conn,
    _persist_learn_suggestions_safe,
    mcp,
)
from tools._shared import ok, safe_tool
from tools.learning import learn_extract, learn_narrative, learn_suggest, learn_validate


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
