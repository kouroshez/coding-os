"""Private sibling of board_os.mcp_tools — import via the kernel, never directly."""

from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

from board_os.config import (
    APPETITE_RE,
    KIND_ENUM,
    PRIORITY_ENUM,
)
from board_os.parser import parse_task
from board_os.sync import sync_one
from thinking_os.tools._shared import fail, ok, safe_tool

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


def _git_commits_for_path(rel_path: str, *, limit: int = 50) -> list[dict]:
    import subprocess

    root = _project_root()
    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "log",
                f"-n{limit}",
                "--format=%H%x1f%ct%x1f%s",
                "--",
                rel_path,
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("git log failed for %s: %s", rel_path, exc)
        return []
    if out.returncode != 0:
        return []
    commits: list[dict] = []
    for raw in out.stdout.splitlines():
        parts = raw.split("\x1f")
        if len(parts) != 3:
            continue
        sha, ct, subject = parts
        try:
            at = int(ct)
        except ValueError:
            at = 0
        commits.append({"sha": sha[:10], "subject": subject, "at": at})
    return commits


def _git_commits_by_task_id(task_id: str, *, exclude: set[str], limit: int = 50) -> list[dict]:
    # Actor-agnostic retroactive link: matches commits by message regardless of
    # source (Hub/terminal/human), without session state or a touch of the .md.
    # The `([^0-9]|$)` guard stops TASK-5 matching TASK-50.
    import subprocess

    if not task_id:
        return []
    root = _project_root()
    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "log",
                "--all",
                "-E",
                f"-n{limit}",
                "--grep",
                f"{task_id}([^0-9]|$)",
                "--format=%H%x1f%ct%x1f%s",
            ],
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("git log --grep failed for %s: %s", task_id, exc)
        return []
    if out.returncode != 0:
        return []
    commits: list[dict] = []
    for raw in out.stdout.splitlines():
        parts = raw.split("\x1f")
        if len(parts) != 3:
            continue
        sha, ct, subject = parts
        if sha[:10] in exclude:
            continue
        try:
            at = int(ct)
        except ValueError:
            at = 0
        commits.append({"sha": sha[:10], "subject": subject, "at": at})
    return commits


def _git_commits_from_worklog(rel_path: str, *, exclude: set[str], limit: int = 50) -> list[dict]:
    # Links work-log SHAs that never touched the .md. Validated in ONE indexed
    # `git cat-file` batch (only type `commit` survives) instead of a per-token
    # `git show` that can stall the loop and false-match a date↔short-sha collision.
    import re as _re
    import subprocess

    root = _project_root()
    try:
        text = (Path(root) / rel_path).read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    cands: list[str] = []
    seen: set[str] = set()
    for cand in _re.findall(r"\b[0-9a-f]{7,40}\b", text):
        if cand in seen:
            continue
        seen.add(cand)
        cands.append(cand)
        if len(cands) >= limit:
            break
    if not cands:
        return []

    try:
        batch = subprocess.run(
            ["git", "-C", str(root), "cat-file", "--batch-check"],
            input="\n".join(cands),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("git cat-file failed for %s: %s", rel_path, exc)
        return []
    if batch.returncode != 0:
        return []

    # Hit line: "<full-objectname> <type> <size>". Miss/ambiguous line:
    # "<input> missing" / "<input> ambiguous" — type slot is not "commit".
    commit_shas = [
        parts[0]
        for parts in (line.split() for line in batch.stdout.splitlines())
        if len(parts) >= 2 and parts[1] == "commit"
    ]
    if not commit_shas:
        return []

    try:
        res = subprocess.run(
            ["git", "-C", str(root), "log", "--no-walk", "--format=%H%x1f%ct%x1f%s", *commit_shas],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.debug("git log --no-walk failed for %s: %s", rel_path, exc)
        return []
    if res.returncode != 0:
        return []

    out: list[dict] = []
    for raw in res.stdout.splitlines():
        parts = raw.split("\x1f")
        if len(parts) != 3:
            continue
        full, ct, subject = parts
        short = full[:10]
        if short in exclude:
            continue
        try:
            at = int(ct)
        except ValueError:
            at = 0
        out.append({"sha": short, "subject": subject, "at": at})
        exclude.add(short)
    return out


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


# ---------- Helpers ----------
