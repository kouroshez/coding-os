#!/usr/bin/env python3
"""
Coding OS — Thinking OS MCP Server (stdio transport).

Agent-agnostic self-learning system for AI coding agents.

This module is the entry point and the public surface: the health tool, the
self-test, and `main()`. The ~140 `cos_*` tools are registered by importing
the `_tools_*` siblings, each of which owns one domain and binds onto the
single FastMCP instance in `_server_runtime`. Importing this module still
registers everything, so `import server` behaves exactly as it did when all
3,159 lines lived here.
"""

from __future__ import annotations

import json
import sys

from _server_runtime import (
    _csv,
    _db_conn,
    _detect_agent_session_default,
    _panel_or_agent_dir,
    _persist_learn_suggestions_safe,
    _record_memory_check_safe,
    logger,
    mcp,
)
from database import get_db_stats, project_root
from tools._shared import apply_module_tool_gating, ok, safe_tool


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
    active_model = "unknown"
    try:
        from embeddings import active_model_name, is_available

        embeddings_available = is_available()
        active_model = active_model_name()
    except ImportError as exc:
        logger.debug("Embeddings module unavailable for health check: %s", exc)

    stats["rag"] = {
        "embeddings_available": embeddings_available,
        "embedding_model": active_model,
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

    # Constitution slice durability: the values layer is surfaced at
    # every SessionStart directly from docs/governance/constitution.md — not from
    # decaying agent memory — so it is non-decaying by construction. A missing file
    # or absent SLICE markers would silently drop the slice; assert it here so
    # `cos doctor` / health flags the regression like a dangling symlink. Fail-open.
    try:
        const_path = project_root() / "docs" / "governance" / "constitution.md"
        present = const_path.is_file()
        slice_markers_ok = False
        if present:
            const_text = const_path.read_text(encoding="utf-8", errors="ignore")
            start = const_text.find("<!-- SLICE:START -->")
            end = const_text.find("<!-- SLICE:END -->")
            # Require non-empty CONTENT between the markers, not just their
            # presence: an empty slice silently delivers no values while a
            # markers-only check would report healthy.
            slice_markers_ok = (
                start != -1
                and end > start
                and const_text[start + len("<!-- SLICE:START -->") : end].strip() != ""
            )
        stats["constitution"] = {
            "present": present,
            "slice_markers_ok": slice_markers_ok,
            "non_decaying": True,
            "repair": None
            if (present and slice_markers_ok)
            else "restore docs/governance/constitution.md with a non-empty <!-- SLICE:START/END --> block so SessionStart can surface the values slice (TASK-491)",
        }
    except Exception as exc:  # pragma: no cover — defensive, never fail the health call
        logger.debug("constitution health check failed: %s", exc)
        stats["constitution"] = {
            "present": False,
            "slice_markers_ok": False,
            "non_decaying": True,
            "repair": f"check_error: {exc}",
        }

    return ok(stats, meta={"layer": "health"})


# ---------------------------------------------------------------------------
# Tool registration — importing each sibling binds its domain onto `mcp`.
# Import-for-side-effect, so the names are re-exported below for callers that
# reach through `server.<tool>` (tests, verify scripts).
# ---------------------------------------------------------------------------
import _tools_docs  # noqa: F401
import _tools_graph_insights  # noqa: F401
import _tools_graph_query  # noqa: F401
import _tools_memory  # noqa: F401
import _tools_routing  # noqa: F401
import _tools_tasks  # noqa: F401
from _tools_memory import (
    cos_learn_extract,
    cos_learn_narrative,
    cos_learn_suggest,
    cos_learn_validate,
    cos_log_query,
    cos_metric_query,
    cos_metric_record,
    cos_metric_trend,
    cos_observation_record,
    thinking_os_details,
    thinking_os_promote_tool,
    thinking_os_search,
    thinking_os_timeline,
)


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


# Re-exported so `server.<name>` keeps resolving after the split (mypy needs
# the explicit list; ruff needs the noqa above).
__all__ = [
    "_csv",
    "_db_conn",
    "_detect_agent_session_default",
    "_panel_or_agent_dir",
    "_persist_learn_suggestions_safe",
    "_record_memory_check_safe",
    "cos_learn_extract",
    "cos_learn_narrative",
    "cos_learn_suggest",
    "cos_learn_validate",
    "cos_log_query",
    "cos_metric_query",
    "cos_metric_record",
    "cos_metric_trend",
    "cos_observation_record",
    "logger",
    "main",
    "mcp",
    "thinking_os_details",
    "thinking_os_health",
    "thinking_os_promote_tool",
    "thinking_os_search",
    "thinking_os_timeline",
]
