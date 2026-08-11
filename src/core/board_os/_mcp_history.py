"""Private sibling of board_os.mcp_tools — import via the kernel, never directly.

`cos_task_history` — the one chronological read that merges status transitions,
field edits, Work Log bullets, and git commits. The git sources live in
`_mcp_git_links` and the edit tool in `_mcp_edit`; both are re-exported here so
the kernel's import list is unchanged.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from board_os.parser import parse_task
from thinking_os.tools._shared import fail, ok, safe_tool

from ._mcp_edit import (
    _WORKLOG_HEADING_RE as _WORKLOG_HEADING_RE,
    _record_task_edit as _record_task_edit,
    _strip_leading_h1 as _strip_leading_h1,
    _worklog_span as _worklog_span,
    cos_task_edit as cos_task_edit,
)
from ._mcp_git_links import (
    _git_commits_by_task_id as _git_commits_by_task_id,
    _git_commits_for_path as _git_commits_for_path,
    _git_commits_from_worklog as _git_commits_from_worklog,
)
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


def _worklog_events(rel_path: str) -> list[dict]:
    # Parse Work Log bullets into timeline events so History and Work Log read as
    # one chronological story instead of two overlapping surfaces.
    import re as _re
    from datetime import datetime, timezone

    root = _project_root()
    try:
        text = (Path(root) / rel_path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    parsed = parse_task(text)
    if parsed is None:
        return []
    line_re = _re.compile(r"^-\s*(\d{4}-\d{2}-\d{2})\s*\[([^\]]+)\]:\s*(.*)$")
    out: list[dict] = []
    for i, ln in enumerate(parsed.work_log_lines):
        m = line_re.match(ln.strip())
        if not m:
            continue
        date_s, actor, note = m.group(1), m.group(2).strip(), m.group(3).strip()
        try:
            # +i keeps same-day bullets in file order under the chronological sort.
            at = (
                int(datetime.strptime(date_s, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
                + i
            )
        except ValueError:
            at = 0
        out.append(
            {
                "type": "worklog",
                "at": at,
                "actor": {
                    "type": "human" if actor == "human" else "agent",
                    "id": actor,
                    "label": actor,
                },
                "text": note,
            }
        )
    return out


@safe_tool
def cos_task_history(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    include_commits: bool = True,
    limit: int = 200,
) -> str:
    """Full actor-attributed task history — creation, status transitions, field edits, and git commits."""
    row = conn.execute(
        "SELECT file_path FROM tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    if row is None:
        return fail("not_found", f"task {task_id} not found")

    events: list[dict] = []

    for r in conn.execute(
        "SELECT old_status, new_status, agent_session, reason, transitioned_at, "
        "override_reason, override_actor FROM task_status_history "
        "WHERE task_id = ? ORDER BY transitioned_at",
        (task_id,),
    ).fetchall():
        old, new, sess, reason, at, ov_reason, ov_actor = r
        events.append(
            {
                "type": "created" if not old else "status",
                "from": old or None,
                "to": new,
                "actor": _actor_view(sess),
                "reason": reason,
                "override_reason": ov_reason,
                "override_actor": ov_actor,
                "at": at,
            }
        )

    if _has_table(conn, "task_edit_history"):
        for r in conn.execute(
            "SELECT field, old_value, new_value, actor_type, actor_id, source, edited_at "
            "FROM task_edit_history WHERE task_id = ? ORDER BY edited_at",
            (task_id,),
        ).fetchall():
            field, oldv, newv, atype, aid, src, at = r
            events.append(
                {
                    "type": "edit",
                    "field": field,
                    "old_value": oldv,
                    "new_value": newv,
                    "actor": {"type": atype, "id": aid, "label": aid or atype},
                    "source": src,
                    "at": at,
                }
            )

    if row[0]:
        events.extend(_worklog_events(row[0]))

    commits: list[dict] = []
    if include_commits and row[0]:
        commits = _git_commits_for_path(row[0], limit=limit)
        seen_shas = {c["sha"] for c in commits}
        for c in commits:
            events.append(
                {"type": "commit", "sha": c["sha"], "subject": c["subject"], "at": c["at"]}
            )
        # Also surface commits referenced in the Work Log (the code commits that
        # did the work but never touched the md file) so they link WITHOUT a task
        # id in the commit message — the file-path link only catches md touches.
        for c in _git_commits_from_worklog(row[0], exclude=seen_shas, limit=limit):
            seen_shas.add(c["sha"])
            events.append(
                {"type": "commit", "sha": c["sha"], "subject": c["subject"], "at": c["at"]}
            )
        # The robust, retroactive, actor-agnostic source: commits whose MESSAGE
        # names this task id (git log --all --grep). Catches Hub/terminal/human
        # commits the path + work-log sources miss when the id is in the subject.
        for c in _git_commits_by_task_id(task_id, exclude=seen_shas, limit=limit):
            events.append(
                {"type": "commit", "sha": c["sha"], "subject": c["subject"], "at": c["at"]}
            )

    events.sort(key=lambda e: e.get("at") or 0)
    if len(events) > limit:
        events = events[-limit:]

    created = next((e for e in events if e["type"] == "created"), None)
    edits = [e for e in events if e["type"] == "edit"]
    contributors = sorted(
        {
            e["actor"]["label"]
            for e in events
            if e.get("type") in {"created", "status", "edit"} and isinstance(e.get("actor"), dict)
        }
    )
    summary = {
        "created_by": created["actor"]["label"] if created else None,
        "created_at": created["at"] if created else None,
        "last_edited_by": edits[-1]["actor"]["label"] if edits else None,
        "last_edited_at": edits[-1]["at"] if edits else None,
        "contributors": contributors,
        "commit_count": len(commits),
    }

    return ok(
        {"task_id": task_id, "events": events, "summary": summary, "count": len(events)},
        meta={"layer": "tasks", "source": "board_os.cos_task_history"},
    )


# ---------- Helpers ----------
