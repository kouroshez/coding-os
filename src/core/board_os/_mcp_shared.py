"""Shared board_os helpers — leaf module: never import mcp_tools at module level.

Id allocation, card shaping, and forge-ref parsing moved to leaves of their own;
this module imports them and re-exports every name, so the `__all__` surface the
MCP modules address as module attrs is unchanged.
"""

from __future__ import annotations

import json  # noqa: F401 — re-exported: mcp_tools imports it from this module
import logging
import os
import re
import sqlite3
import time  # noqa: F401 — re-exported: mcp_tools imports it from this module

# The full original mcp_tools import surface is kept here (and re-exported by
# the facade) because tests and consumers address these names as module attrs.
from datetime import datetime
from pathlib import Path

from board_os._agent_runtime import SYSTEM_SESSION_PREFIX
from board_os.config import (
    APPETITE_RE,
    KIND_ENUM,
    PRIORITY_ENUM,
    READY_LABEL,
    STATUS_ENUM,
    TASK_ID_FORMAT_RE,
    load_config,
)
from board_os.parser import parse_task
from board_os.sync import sync_one
from board_os.workflow import (
    _format_yaml_scalar_token,
    _has_task_dependencies_table,
    check_wip,
    dependents_of,
    incomplete_dependencies,
    patch_task_frontmatter_scalars,
    transition,
    validate_dependencies_no_cycle,
)
from thinking_os.tools._shared import (
    TOKEN_BUDGET_CHARS,
    _budget_size,
    fail,
    ok,
    safe_tool,
)

from ._mcp_cards import (
    _BOARD_SELECT,
    _COMPLETION_EVIDENCE_RE,
    _completion_evidence,
    _flag_stale,
    _humanize_duration,
    _last_log_line,
    _sla_threshold_seconds,
    _status_dwell_seconds,
    _task_card,
)
from ._mcp_forge import _detect_forge, _normalize_external_ref
from ._mcp_task_ids import (
    _TASK_ID_ALLOCATORS,
    _allocate_with_prefix,
    _derive_ns_from_git,
    _LocalAllocator,
    _namespace_segment,
    _NamespacedAllocator,
    _next_task_id,
    _resolve_task_id_allocator,
)

logger = logging.getLogger("coding_os.board_os.mcp_tools")

_SLUG_RE = re.compile(r"[^a-z0-9]+")


# ---------- Internal helpers ----------


def _project_root() -> Path:
    from thinking_os.database import project_root

    return project_root()


def _current_config():
    try:
        return load_config(_project_root())
    except FileNotFoundError:
        return None


def _slugify(title: str, *, max_len: int = 60) -> str:
    slug = _SLUG_RE.sub("-", title.lower()).strip("-")
    return slug[:max_len] or "untitled"


def cos_task_link(conn: sqlite3.Connection, task_id: str, ref: str) -> dict:
    """Link a task to a forge issue/PR via the optional external_ref field."""
    row = conn.execute("SELECT file_path FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if not row:
        return fail("not_found", f"task {task_id} not found")
    project_root = _project_root()
    file_path = project_root / row[0]
    if not file_path.exists():
        return fail("not_found", f"file missing: {file_path}")
    normalized = _normalize_external_ref(ref, project_root)
    if not normalized:
        return fail(
            "validation",
            f"could not parse a forge ref from {ref!r} — use e.g. 42, github#42, or an issue URL",
        )
    patch_task_frontmatter_scalars(file_path, {"external_ref": normalized})
    return ok({"task_id": task_id, "external_ref": normalized, "meta": {"layer": "tasks"}})


def _agent_label(agent_session: str | None) -> str:
    # Detection lives in _agent_runtime.detect_agent so cli/board_commands.py and
    # this module share one code path; shell counterpart is core/hooks/cos-env.sh.
    from ._agent_runtime import detect_agent

    return detect_agent(agent_session)


def _resolve_attribution(agent_session: str | None) -> str | None:
    # Without this, task_status_history.agent_session is NULL and the board UI
    # renders the human "H" glyph for agent-driven creates. Reads $COS_SESSION_FILE
    # (set by every adapter via session-context.sh), so the fix is adapter-agnostic.
    from ._agent_runtime import resolve_agent_session

    return resolve_agent_session(agent_session)


def _assign_guard(
    file_path: Path | None,
    agent_session: str | None,
    force: bool,
) -> str | None:
    # Opt-in + backward-compatible: no `assignee:` field → movable by anyone.
    # When set, only that session (or any session of the same agent) may move it;
    # force=True or COS_ASSIGN_OVERRIDE=1 bypasses. Returns an error msg or None.
    if force or os.environ.get("COS_ASSIGN_OVERRIDE") == "1":
        return None
    if file_path is None or not file_path.exists():
        return None
    try:
        head = file_path.read_text(encoding="utf-8")[:2000]
    except OSError:
        return None
    match = re.search(r"^assignee:[ \t]*(.+?)[ \t]*$", head, re.MULTILINE)
    if not match:
        return None
    assignee = match.group(1).strip().strip('"').strip("'")
    if assignee.lower() in ("", "any", "anyone", "unassigned", "null", "~"):
        return None

    from ._agent_runtime import detect_agent

    mover = (agent_session or "").strip()
    if assignee == mover:
        return None
    mover_agent = detect_agent(mover)
    if mover_agent != "agent" and detect_agent(assignee) == mover_agent:
        return None
    return (
        f"task is assigned to {assignee!r} — current mover is "
        f"{mover or 'unattributed'!r}. Re-assign the task (edit its "
        "`assignee:` frontmatter) or override with force=True / "
        "COS_ASSIGN_OVERRIDE=1."
    )


# ---------- cos_task_create ----------


def _commits_referencing(task_id: str, project_root: Path) -> int | None:
    # None = unverifiable (no git / error) so callers fail SAFE — treat as "has
    # evidence", never auto-reclaim on a signal we couldn't check. Trailing
    # non-digit boundary stops also matching
    import subprocess

    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(project_root),
                "log",
                "--all",
                "-E",
                f"--max-count={_COMMIT_SCAN_CAP}",
                "--grep",
                f"{task_id}([^0-9]|$)",
                "--oneline",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return sum(1 for line in out.stdout.splitlines() if line.strip())


# Cap on how many matching commits git enumerates per scan — bounds the history
# walk at 1M+ commits. Reconciliation only needs "0 vs >0" evidence, so a count
# capped at this value is sufficient (and reported as "at least N").
_COMMIT_SCAN_CAP = 500
# Cap on a single reclaim/reconcile sweep — the rest drains on the next run.
_STRANDED_SCAN_LIMIT = 1000


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()
        is not None
    )


def _actor_view(agent_session: str | None) -> dict:
    from ._agent_runtime import detect_agent

    if not agent_session:
        return {"type": "human", "id": "human", "label": "human"}
    label = detect_agent(agent_session)
    if label in ("human", "system"):
        actor_type = label
    else:
        actor_type = "agent"
    return {
        "type": actor_type,
        "id": agent_session,
        "label": label,
    }


def _parse_since(since: str) -> float:
    m = re.match(r"^(\d+)([mhdw])$", since)
    if not m:
        return 24.0
    n, unit = int(m.group(1)), m.group(2)
    return {"m": n / 60.0, "h": float(n), "d": n * 24.0, "w": n * 24.0 * 7.0}[unit]


# ---------- Cycle validation tool (exposed for hooks) ----------


def check_cycle(conn: sqlite3.Connection, task_id: str, new_deps: list[str]) -> list[str]:
    """Thin passthrough to workflow.validate_dependencies_no_cycle."""
    return validate_dependencies_no_cycle(conn, task_id, new_deps)


__all__ = [
    "APPETITE_RE",
    "KIND_ENUM",
    "PRIORITY_ENUM",
    "READY_LABEL",
    "STATUS_ENUM",
    "SYSTEM_SESSION_PREFIX",
    "TASK_ID_FORMAT_RE",
    "TOKEN_BUDGET_CHARS",
    "_BOARD_SELECT",
    "_COMMIT_SCAN_CAP",
    "_COMPLETION_EVIDENCE_RE",
    "_SLUG_RE",
    "_STRANDED_SCAN_LIMIT",
    "_TASK_ID_ALLOCATORS",
    "Path",
    "_LocalAllocator",
    "_NamespacedAllocator",
    "_actor_view",
    "_agent_label",
    "_allocate_with_prefix",
    "_assign_guard",
    "_budget_size",
    "_commits_referencing",
    "_completion_evidence",
    "_current_config",
    "_derive_ns_from_git",
    "_detect_forge",
    "_flag_stale",
    "_format_yaml_scalar_token",
    "_has_table",
    "_has_task_dependencies_table",
    "_humanize_duration",
    "_last_log_line",
    "_namespace_segment",
    "_next_task_id",
    "_normalize_external_ref",
    "_parse_since",
    "_project_root",
    "_resolve_attribution",
    "_resolve_task_id_allocator",
    "_sla_threshold_seconds",
    "_slugify",
    "_status_dwell_seconds",
    "_task_card",
    "annotations",
    "check_cycle",
    "check_wip",
    "cos_task_link",
    "datetime",
    "dependents_of",
    "fail",
    "incomplete_dependencies",
    "load_config",
    "logger",
    "ok",
    "parse_task",
    "patch_task_frontmatter_scalars",
    "safe_tool",
    "sync_one",
    "transition",
    "validate_dependencies_no_cycle",
]
