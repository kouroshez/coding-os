"""Private sibling of board_os.mcp_tools — import via the kernel, never directly.

Appending one checkpoint to a task's Work Log — the persistent progress record
the next agent inherits.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timezone

from board_os.sync import sync_one  # type: ignore[import-not-found]
from thinking_os.tools._shared import fail, ok, safe_tool  # type: ignore[import-not-found]

from ._mcp_history import _WORKLOG_HEADING_RE
from ._mcp_shared import (  # noqa: F401
    _BOARD_SELECT,
    _COMMIT_SCAN_CAP,
    _COMPLETION_EVIDENCE_RE,
    _SLUG_RE,
    _STRANDED_SCAN_LIMIT,
    _TASK_ID_ALLOCATORS,
    _actor_view,
    _agent_label,
    _allocate_with_prefix,
    _assign_guard,
    _commits_referencing,
    _completion_evidence,
    _current_config,
    _derive_ns_from_git,
    _detect_forge,
    _flag_stale,
    _has_table,
    _humanize_duration,
    _last_log_line,
    _LocalAllocator,
    _namespace_segment,
    _NamespacedAllocator,
    _next_task_id,
    _normalize_external_ref,
    _parse_since,
    _project_root,
    _resolve_attribution,
    _resolve_task_id_allocator,
    _sla_threshold_seconds,
    _slugify,
    _status_dwell_seconds,
    _task_card,
    check_cycle,
    cos_task_link,
    logger,
)

# ---------- cos_work_log_append ----------


_WORKLOG_SUMMARY_CAP = 120


def _truncate_summary(text: str, cap: int = _WORKLOG_SUMMARY_CAP) -> str:
    # Trim at the last word boundary within the cap and mark the loss with a
    # single ellipsis, so a long note reads as deliberately shortened rather
    # than silently chopped mid-word. The ellipsis counts toward the cap, so
    # the returned string is always <= cap (the documented Work Log contract).
    flat = text.strip().replace("\n", " ")
    if len(flat) <= cap:
        return flat
    clipped = flat[: cap - 1].rstrip()
    boundary = clipped.rfind(" ")
    if boundary > 0:
        clipped = clipped[:boundary].rstrip()
    return f"{clipped}…"


@safe_tool
def cos_work_log_append(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    summary: str | None = None,
    note: str | None = None,
    agent_session: str | None = None,
    source: str = "manual",
) -> str:
    """Append one line to a task's Work Log section in the MD file."""
    # G38: accept `note` as alias of `summary` — many task-driver
    # callers (and docs) pass `note=...`; the prior signature only
    # honoured `summary`, producing a 422 validation error.
    if summary is None and note is not None:
        summary = note
    if not isinstance(summary, str) or not summary.strip():
        return fail("validation", "summary (or note) is required")
    row = conn.execute(
        "SELECT file_path FROM tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    if row is None or not row[0]:
        return fail("not_found", f"task {task_id} has no file_path")
    file_path = _project_root() / row[0]
    if not file_path.exists():
        return fail("not_found", f"file missing: {file_path}")

    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    agent_label = _agent_label(agent_session)
    summary_trunc = _truncate_summary(summary)
    line = f"- {date} [{agent_label}]: {summary_trunc}"

    content = file_path.read_text(encoding="utf-8")
    marker = "## Work Log"
    # Match the heading anchored at line start, not a `## Work Log` mention
    # inside prose (e.g. an Acceptance bullet) which a plain substring search
    # would hit first — landing the entry ABOVE the real section.
    head = _WORKLOG_HEADING_RE.search(content)
    if head is None:
        # Append a Work Log section at the end.
        new_content = content.rstrip() + f"\n\n{marker}\n{line}\n"
    else:
        # Insert at the end of the Work Log section (before the next H2
        # heading if any, else at EOF), both anchored at line start.
        nxt = re.search(r"(?m)^## ", content[head.end() :])
        insert_at = head.end() + nxt.start() if nxt else len(content)
        before = content[:insert_at].rstrip()
        after = content[insert_at:]
        new_content = f"{before}\n{line}\n{after}"
    file_path.write_text(new_content, encoding="utf-8")

    # Re-sync to pick up the new log line.
    sync_one(conn, file_path, project_root=_project_root())

    return ok(
        {
            "task_id": task_id,
            "line_appended": line,
            "source": source,
        },
        meta={"layer": "tasks", "source": "board_os.cos_work_log_append"},
    )
