"""Process-wide runtime for the thinking_os MCP server.

Leaf module: the FastMCP instance, logging, the DB connection, and the
helpers the tool modules share. It imports none of them back, so any
sibling can be imported first without a cycle.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from database import init_db
from mcp.server.fastmcp import FastMCP
from tools._shared import safe_tool

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
# Agent-session resolver — fix for AGENT STREAM "H" label
# ---------------------------------------------------------------------------


def _detect_agent_session_default() -> str | None:
    """Best-effort fallback for MCP tools that accept `agent_session`."""
    import os as _os
    from pathlib import Path as _P

    explicit = (_os.environ.get("COS_AGENT_SESSION_ID") or "").strip()
    if explicit:
        return explicit

    def _first_line(p: _P) -> str:
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


def _csv(value: str) -> list[str] | None:
    """Parse a comma-separated CLI-style string into a clean list or None."""
    if not value:
        return None
    parts = [p.strip() for p in value.split(",") if p.strip()]
    return parts or None


# ---------------------------------------------------------------------------
# graph_os availability probe. The cos_graph_* wrappers in _tools_graph_*.py
# import `_graph_tools` from here so the optional dependency is resolved once.
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


def _graph_unavailable() -> str:
    """Envelope the agent sees when graph_os tools can't be imported."""
    return json.dumps(
        {
            "ok": False,
            "error": {
                "category": "unavailable",
                "retryable": False,
                "message": "graph_os package not importable; install graph_os extra",
            },
        }
    )


def register_unavailable_stubs(names: tuple[str, ...]) -> None:
    """Register deterministic `unavailable` envelopes for missing graph tools."""
    for tool_name in names:

        def _make_stub(name: str):
            @mcp.tool(
                name=name,
                annotations={"title": f"{name} (unavailable)", "readOnlyHint": True},
            )
            @safe_tool
            def _stub(*_args: object, **_kwargs: object) -> str:
                return _graph_unavailable()

            return _stub

        _make_stub(tool_name)
