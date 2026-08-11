"""Private sibling of board_os.mcp_tools — import via the kernel, never directly.

`cos_task_edit` and the actor-attributed edit trail it writes: frontmatter field
validation, the per-field `task_edit_history` record, and the Work-Log-preserving
body merge.
"""

from __future__ import annotations

import re
import sqlite3
import time

from board_os.config import (
    APPETITE_RE,
    KIND_ENUM,
    PRIORITY_ENUM,
)
from board_os.sync import sync_one
from thinking_os.tools._shared import fail, ok, safe_tool

from ._mcp_shared import (
    _current_config,
    _has_table,
    _project_root,
    _resolve_attribution,
    logger,
)

# ---------- cos_task_edit ----------


def _record_task_edit(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    field: str,
    old: str | None,
    new: str | None,
    actor_type: str,
    actor_id: str | None,
    source: str,
) -> None:
    if not _has_table(conn, "task_edit_history"):
        return
    try:
        conn.execute(
            "INSERT INTO task_edit_history "
            "(task_id, field, old_value, new_value, actor_type, actor_id, source, edited_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (task_id, field, old, new, actor_type, actor_id, source, int(time.time())),
        )
        conn.commit()
    except sqlite3.Error as exc:
        logger.debug("task_edit_history insert failed for %s.%s: %s", task_id, field, exc)


_WORKLOG_HEADING_RE = re.compile(r"(?im)^##[ \t]+Work Log[ \t]*$")


def _worklog_span(body: str) -> str:
    m = _WORKLOG_HEADING_RE.search(body)
    if m is None:
        return ""
    nxt = re.search(r"(?m)^## ", body[m.end() :])
    end = m.end() + nxt.start() if nxt else len(body)
    return body[m.start() : end].rstrip("\n")


def _strip_leading_h1(body: str) -> str:
    return re.sub(r"^\s*#\s+.+\n+", "", body.lstrip("\n")).strip()


@safe_tool
def cos_task_edit(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    title: str | None = None,
    priority: str | None = None,
    swimlane: str | None = None,
    appetite: str | None = None,
    epic: str | None = None,
    labels: list[str] | None = None,
    body: str | None = None,
    actor_type: str = "agent",
    actor_id: str | None = None,
    source: str = "mcp",
) -> str:
    """Edit a task's frontmatter fields and/or body, recording each change to the actor-attributed edit history."""
    from board_os.parser import _FRONTMATTER_RE, extract_frontmatter

    row = conn.execute(
        "SELECT file_path FROM tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    if row is None or not row[0]:
        return fail("not_found", f"task {task_id} not found")
    file_path = _project_root() / row[0]
    if not file_path.exists():
        return fail("not_found", f"file missing: {file_path}")

    content = file_path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(content)
    fm = extract_frontmatter(content)
    if m is None or fm is None:
        return fail("validation", f"{task_id} is not in lean frontmatter format")
    current_body = m.group("body")

    config = _current_config()
    if swimlane is not None and config is not None and swimlane not in config.swimlane_ids:
        return fail(
            "validation",
            f"swimlane {swimlane!r} not in config; valid: {sorted(config.swimlane_ids)}",
        )
    if priority is not None and priority not in PRIORITY_ENUM:
        return fail("validation", f"priority {priority!r} not in {sorted(PRIORITY_ENUM)}")
    if appetite is not None and not APPETITE_RE.match(appetite):
        return fail("validation", f"appetite {appetite!r} bad shape")
    if title is not None and not title.strip():
        return fail("validation", "title must be non-empty")
    if labels is not None:
        for lbl in labels:
            if lbl in KIND_ENUM:
                return fail(
                    "validation",
                    f"label {lbl!r} collides with KIND_ENUM — use kind, not labels",
                )

    resolved_actor = actor_id or _resolve_attribution(None)
    changed: list[str] = []

    def _maybe(field: str, new_val: object) -> None:
        if new_val is None or new_val == fm.get(field):
            return
        old_val = fm.get(field)
        fm[field] = new_val
        _record_task_edit(
            conn,
            task_id=task_id,
            field=field,
            old=None if old_val is None else str(old_val),
            new=str(new_val),
            actor_type=actor_type,
            actor_id=resolved_actor,
            source=source,
        )
        changed.append(field)

    _maybe("title", title)
    _maybe("priority", priority)
    _maybe("swimlane", swimlane)
    _maybe("appetite", appetite)
    _maybe("epic", epic)

    if labels is not None and list(labels) != list(fm.get("labels") or []):
        old_labels = fm.get("labels") or []
        fm["labels"] = list(labels)
        _record_task_edit(
            conn,
            task_id=task_id,
            field="labels",
            old=", ".join(str(x) for x in old_labels),
            new=", ".join(labels),
            actor_type=actor_type,
            actor_id=resolved_actor,
            source=source,
        )
        changed.append("labels")

    new_body = current_body
    if body is not None:
        incoming = body
        # The board drawer's body is a snapshot; a cos_work_log_append can land
        # between its fetch and this save. Swap the client's (possibly stale)
        # "## Work Log" for the FRESH on-disk section in place, so a concurrent
        # append is never lost and the section never reorders.
        fresh_wl = _worklog_span(current_body)
        if fresh_wl:
            stale_wl = _worklog_span(incoming)
            if stale_wl and stale_wl != fresh_wl:
                incoming = incoming.replace(stale_wl, fresh_wl, 1)
            elif not stale_wl:
                incoming = incoming.rstrip("\n") + "\n\n" + fresh_wl + "\n"
        # Compare H1-normalized: the drawer strips the leading H1 (the write
        # path re-prepends the canonical one), so a body that differs only by
        # that H1 must not record a phantom body change.
        if _strip_leading_h1(incoming) != _strip_leading_h1(current_body):
            import hashlib

            new_body = incoming
            _record_task_edit(
                conn,
                task_id=task_id,
                field="body",
                old=hashlib.sha1(current_body.encode("utf-8")).hexdigest()[:12],
                new=hashlib.sha1(incoming.encode("utf-8")).hexdigest()[:12],
                actor_type=actor_type,
                actor_id=resolved_actor,
                source=source,
            )
            changed.append("body")

    if not changed:
        return ok(
            {"task_id": task_id, "changed": []},
            meta={"layer": "tasks", "source": "board_os.cos_task_edit"},
        )

    # Normalise the canonical H1 (`# TASK-NNN: <title>`) from the current
    # frontmatter title: a panel body edit arrives H1-stripped (the drawer
    # removes it for display) and a title change must propagate to the H1.
    # Strip any leading H1 from the incoming body, then prepend the canonical.
    title_now = str(fm.get("title") or task_id)
    body_inner = re.sub(r"^\s*#\s+.+\n+", "", new_body.lstrip("\n"))
    from ._mcp_create import _render_lean_frontmatter

    new_content = (
        _render_lean_frontmatter(fm)
        + f"\n\n# {task_id}: {title_now}\n\n"
        + body_inner.strip("\n")
        + "\n"
    )
    file_path.write_text(new_content, encoding="utf-8")
    sync_one(conn, file_path, project_root=_project_root())

    return ok(
        {
            "task_id": task_id,
            "changed": changed,
            "actor": {"type": actor_type, "id": resolved_actor},
        },
        meta={"layer": "tasks", "source": "board_os.cos_task_edit"},
    )
