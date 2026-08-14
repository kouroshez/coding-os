"""Private sibling of board_os.mcp_tools — import via the kernel, never directly.

Recovery of tasks an agent abandoned: which sessions are still alive, what a
stranded card most likely means, and the reclaim / reconcile / stale-archive
passes that act on that verdict.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

from board_os._agent_runtime import SYSTEM_SESSION_PREFIX  # type: ignore[import-not-found]
from board_os.config import (
    READY_LABEL,
)
from board_os.sync import sync_one  # type: ignore[import-not-found]
from board_os.workflow import (  # type: ignore[import-not-found]
    transition,
)
from thinking_os.tools._shared import ok, safe_tool  # type: ignore[import-not-found]

from ._mcp_lifecycle import _labels_list_from_json, _patch_labels_line
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


def _active_session_ids(now: float, window: int = 1800) -> set[str]:
    # Reads agent-presence JSON under $COS_STATE_DIR/<agent>/sessions/*.json
    # (written by agent-presence.sh). Missing/unreadable presence → "no active
    # sessions", so reclaim falls back to the idle-only signal.
    ids: set[str] = set()
    state_dir = os.environ.get("COS_STATE_DIR") or str(_project_root() / ".coding-os")
    base = Path(state_dir)
    if not base.is_dir():
        return ids
    for sess_dir in base.glob("*/sessions"):
        for jf in sess_dir.glob("*.json"):
            try:
                d = json.loads(jf.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if d.get("ended_at"):
                continue
            last = 0
            for key in ("last_tool_at", "last_prompt_at", "started_at"):
                val = d.get(key)
                if isinstance(val, (int, float)):
                    last = max(last, int(val))
            if last and (now - last) < window:
                sid = d.get("session_id")
                if sid:
                    ids.add(str(sid))
    return ids


def _commits_referencing_batch(task_ids: list[str], project_root: Path) -> dict[str, int | None]:
    # One history walk for many ids — replaces N per-task subprocesses. All-None
    # when git is unavailable so callers fail SAFE (unverifiable = has evidence).
    import re
    import subprocess

    ids = [t for t in dict.fromkeys(task_ids) if t]
    if not ids:
        return {}
    counts: dict[str, int | None] = dict.fromkeys(ids, 0)
    grep_args: list[str] = []
    for tid in ids:
        grep_args += ["--grep", f"{tid}([^0-9]|$)"]
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
                *grep_args,
                "--format=%s",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return dict.fromkeys(ids)
    if out.returncode != 0:
        return dict.fromkeys(ids)
    patterns = {tid: re.compile(re.escape(tid) + r"([^0-9]|$)") for tid in ids}
    for line in out.stdout.splitlines():
        for tid, pat in patterns.items():
            if pat.search(line):
                counts[tid] += 1
    return counts


def _has_work_log(work_log_json: object) -> bool:
    try:
        return bool(json.loads(work_log_json or "[]"))
    except (json.JSONDecodeError, TypeError):
        return False


def _classify_stranded(status: str, commits: int | None, has_work_log: bool) -> str:
    # commits is None = unverifiable (no git / error) — counted AS evidence so a
    # task is never called abandoned on a signal we couldn't check.
    has_commit_evidence = commits is None or commits > 0
    if status == "testing" and (has_commit_evidence or has_work_log):
        return "likely_complete"
    if status == "in_progress" and commits == 0 and not has_work_log:
        return "likely_abandoned"
    return "needs_review"


def _reconcile_recommendation(task_id: str, classification: str, commits: int) -> str:
    n = "?" if commits is None else commits
    if classification == "zombie_icebox":
        return (
            f"Work log claims finished work but the card never left icebox. "
            f"Verify the change is live, then `cos task-start {task_id}` -> testing -> "
            f"`cos task-done {task_id}`; if the claim is wrong, resume or park deliberately."
        )
    if classification == "likely_complete":
        return (
            f"Looks finished ({n} commit(s) reference it, reached testing). "
            f"Review acceptance, then `cos task-done {task_id}`; if not actually "
            f"done, `cos task-start {task_id}` to resume."
        )
    if classification == "likely_abandoned":
        return (
            f"No committed progress — `cos task-cancel {task_id} --park` to shelve, "
            f"or `cos task-start {task_id}` to resume."
        )
    return f"Review with `cos task-show {task_id}` -> complete, resume, or park."


@safe_tool
def cos_task_reclaim(
    conn: sqlite3.Connection,
    *,
    idle_hours: int | None = None,
    dry_run: bool = False,
    agent_session: str | None = None,
) -> str:
    """Reclaim zombie in_progress/testing/emergency tasks (idle + owner inactive); testing->in_progress, else->icebox."""
    config = _current_config()
    default_threshold_h = (
        idle_hours
        if idle_hours is not None
        else (config.workflow_policy.reclaim_idle_hours if config is not None else 24)
    )

    def _threshold_for(status: str) -> int:
        # Per-status idle window. `testing` is mid-flight work funneled there by
        # the testing-first protocol, so reclaim it sooner than a generic
        # in_progress zombie. An explicit idle_hours arg overrides all statuses.
        if idle_hours is not None or config is None:
            return default_threshold_h
        if status == "testing":
            t = config.workflow_policy.testing_reclaim_idle_hours
            return t if t > 0 else config.workflow_policy.reclaim_idle_hours
        return config.workflow_policy.reclaim_idle_hours

    now = time.time()
    active = _active_session_ids(now)
    project_root = _project_root()

    # Widened from in_progress-only (RC3): a `testing` zombie was previously
    # un-reclaimable by every path, which is exactly where the protocol parks
    # near-done work at the moment of session death.
    rows = conn.execute(
        "SELECT task_id, agent_session, started_at, file_path, status, work_log_last_5 "
        "FROM tasks WHERE status IN ('in_progress', 'testing', 'emergency') "
        "ORDER BY started_at LIMIT ?",
        (_STRANDED_SCAN_LIMIT,),
    ).fetchall()
    # Batch the per-testing-task git lookup into ONE history walk (was N
    # subprocesses, each O(history) at 1M commits).
    from . import mcp_tools as _kernel

    commits_by_task = _kernel._commits_referencing_batch(
        [r[0] for r in rows if r[4] == "testing"], project_root
    )

    reclaimed: list[dict] = []
    skipped_for_review: list[dict] = []
    for task_id, owner, started_at, rel, status, work_log in rows:
        hist = conn.execute(
            "SELECT MAX(transitioned_at) FROM task_status_history WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        last_activity = max(
            int(started_at or 0),
            int(hist[0]) if hist and hist[0] else 0,
        )
        # No activity signal at all → too risky to reclaim; skip.
        if last_activity == 0:
            continue
        threshold_h = _threshold_for(status)
        idle_s = now - last_activity
        if idle_s < threshold_h * 3600:
            continue
        # Owner still actively present → never reclaim its work.
        if owner and owner in active:
            continue

        # Don't blindly recycle a probably-FINISHED task. A testing
        # zombie with committed/logged work is almost certainly done — the agent
        # just forgot task-done. Leave it in testing for review (cos_task_reconcile
        # surfaces it) instead of recycling it to in_progress.
        if status == "testing":
            commits = commits_by_task.get(task_id)
            # None = unverifiable (no git) → counts as evidence so we never
            # recycle a testing card on a signal we could not check.
            if _has_work_log(work_log) or commits is None or commits > 0:
                skipped_for_review.append({"task_id": task_id, "previous_owner": owner})
                continue

        # Status-aware destination: a testing zombie is near-done, so return it
        # to in_progress (a legal unforced edge) to resume the work rather than
        # dumping it to the backlog; in_progress/emergency zombies go to icebox.
        dest = "in_progress" if status == "testing" else "icebox"
        idle_h = round(idle_s / 3600, 1)
        if dry_run:
            reclaimed.append(
                {
                    "task_id": task_id,
                    "previous_owner": owner,
                    "idle_hours": idle_h,
                    "from_status": status,
                    "to_status": dest,
                }
            )
            continue

        file_path = project_root / rel if rel else None
        # Only a backlog-bound (icebox) reclaim needs the ready label so the
        # card stays pullable; a testing->in_progress reclaim keeps its labels.
        if dest == "icebox" and file_path is not None and file_path.exists():
            cur_labels = _labels_list_from_json(
                conn.execute(
                    "SELECT labels_json FROM tasks WHERE task_id = ?", (task_id,)
                ).fetchone()[0]
            )
            if READY_LABEL not in cur_labels:
                cur_labels.append(READY_LABEL)
                try:
                    _patch_labels_line(file_path, cur_labels)
                    sync_one(conn, file_path, project_root=project_root)
                except (OSError, ValueError) as exc:
                    logger.debug("reclaim label patch failed for %s: %s", task_id, exc)

        result = transition(
            conn,
            task_id,
            dest,
            reason=f"reclaim: {status} idle {idle_h}h, owner session inactive -> {dest}",
            # Unattended runs (nightly daemon) pass no session; attribute the
            # healing to the system actor, not the human fallback.
            agent_session=agent_session or f"{SYSTEM_SESSION_PREFIX}-reclaim",
            force=True,
            config=config,
            file_path=file_path,
        )
        if result.ok:
            reclaimed.append(
                {
                    "task_id": task_id,
                    "previous_owner": owner,
                    "idle_hours": idle_h,
                    "from_status": status,
                    "to_status": dest,
                }
            )

    return ok(
        {
            "reclaimed": reclaimed,
            "count": len(reclaimed),
            "skipped_for_review": skipped_for_review,
            "dry_run": dry_run,
            "idle_hours_threshold": default_threshold_h,
            "active_sessions": len(active),
        },
        meta={"layer": "tasks", "source": "board_os.cos_task_reclaim"},
    )


@safe_tool
def cos_task_reconcile(conn: sqlite3.Connection, *, include_active: bool = False) -> str:
    """Triage stranded in_progress/testing tasks and icebox zombies (completion evidence, no lifecycle) — read-only."""
    now = time.time()
    active = _active_session_ids(now)
    project_root = _project_root()
    rows = conn.execute(
        "SELECT task_id, agent_session, status, started_at, work_log_last_5, "
        "  (SELECT MAX(transitioned_at) FROM task_status_history h "
        "   WHERE h.task_id = tasks.task_id) "
        "FROM tasks WHERE status IN ('in_progress', 'testing', 'emergency') "
        "ORDER BY status DESC, task_id LIMIT ?",
        (_STRANDED_SCAN_LIMIT,),
    ).fetchall()
    # Pre-filter to the rows we'll actually triage (default = stranded only),
    # then batch the git lookup into ONE history walk instead of one subprocess
    # per row.
    triaged = [r for r in rows if include_active or not (r[1] and r[1] in active)]
    # Zombies: icebox cards whose work log already claims finished work. The
    # commit-subject count is NOT the signal here — the card-filing commit
    # mentions every task id, so only the work-log claim distinguishes a zombie.
    zombie_rows = conn.execute(
        "SELECT task_id, agent_session, status, started_at, work_log_last_5, "
        "  (SELECT MAX(transitioned_at) FROM task_status_history h "
        "   WHERE h.task_id = tasks.task_id) "
        "FROM tasks WHERE status = 'icebox' AND work_log_last_5 IS NOT NULL "
        "ORDER BY task_id LIMIT ?",
        (_STRANDED_SCAN_LIMIT,),
    ).fetchall()
    zombies = [r for r in zombie_rows if _completion_evidence(r[4])]
    from . import mcp_tools as _kernel

    commits_by_task = _kernel._commits_referencing_batch(
        [r[0] for r in triaged] + [r[0] for r in zombies], project_root
    )
    items: list[dict] = []
    for task_id, owner, status, started_at, work_log, last_tx in triaged + zombies:
        owner_active = bool(owner and owner in active)
        commits = commits_by_task.get(task_id)
        has_wl = _has_work_log(work_log)
        if status == "icebox":
            classification = "zombie_icebox"
        else:
            classification = _classify_stranded(status, commits, has_wl)
        dwell = _status_dwell_seconds(now, started_at, last_tx)
        items.append(
            {
                "task_id": task_id,
                "status": status,
                "previous_owner": owner,
                "owner_active": owner_active,
                "commits_referencing": commits,
                "has_work_log": has_wl,
                "status_dwell_seconds": dwell,
                "status_dwell_human": _humanize_duration(dwell),
                "classification": classification,
                "recommendation": _reconcile_recommendation(task_id, classification, commits),
            }
        )
    summary = {
        "likely_complete": sum(1 for i in items if i["classification"] == "likely_complete"),
        "likely_abandoned": sum(1 for i in items if i["classification"] == "likely_abandoned"),
        "needs_review": sum(1 for i in items if i["classification"] == "needs_review"),
        "zombie_icebox": sum(1 for i in items if i["classification"] == "zombie_icebox"),
    }
    return ok(
        {"stranded": items, "count": len(items), "summary": summary},
        meta={"layer": "tasks", "source": "board_os.cos_task_reconcile"},
    )


_KEEP_LABELS = ("keep", "parked")


def _archive_stale_sweep(conn: sqlite3.Connection, config) -> list[dict]:
    # OFF by default: runs only when a status's *_auto_archive_days knob is > 0,
    # so a fresh project never silently deletes backlog. keep/parked labels exempt
    # a card; archive is reversible (archive->icebox is legal). Fail-soft per card.
    if config is None:
        return []
    policy = config.workflow_policy
    plans: list[tuple[str, int]] = []
    if getattr(policy, "icebox_auto_archive_days", 0) > 0:
        plans.append(("icebox", policy.icebox_auto_archive_days * 86400))
    if getattr(policy, "complete_auto_archive_days", 0) > 0:
        plans.append(("complete", policy.complete_auto_archive_days * 86400))
    if not plans:
        return []

    now = time.time()
    project_root = _project_root()
    archived: list[dict] = []
    for status, threshold_s in plans:
        rows = conn.execute(
            "SELECT task_id, started_at, file_path, labels_json, "
            "  (SELECT MAX(transitioned_at) FROM task_status_history h "
            "   WHERE h.task_id = tasks.task_id) "
            "FROM tasks WHERE status = ? "
            "ORDER BY started_at ASC LIMIT ?",  # oldest first; rest drains next run
            (status, _STRANDED_SCAN_LIMIT),
        ).fetchall()
        for task_id, started_at, rel, labels_json, last_tx in rows:
            dwell = _status_dwell_seconds(now, started_at, last_tx)
            if dwell is None or dwell < threshold_s:
                continue
            if any(lbl in _KEEP_LABELS for lbl in _labels_list_from_json(labels_json)):
                continue
            file_path = project_root / rel if rel else None
            result = transition(
                conn,
                task_id,
                "archive",
                reason=f"auto-archive: {status} idle {round(dwell / 86400, 1)}d",
                # System attribution, never None — a NULL session renders as the
                # human operator in the stream panel (hub-architecture.md
                # § Actor attribution contract).
                agent_session=f"{SYSTEM_SESSION_PREFIX}-auto-archive",
                force=True,
                config=config,
                file_path=file_path,
            )
            if result.ok:
                archived.append(
                    {"task_id": task_id, "from_status": status, "age_days": round(dwell / 86400, 1)}
                )
            else:
                # Surface per-task failures instead of silently dropping them so
                # the daily "N archived" count can't hide stranded cards.
                logger.warning("auto-archive transition failed for %s (%s)", task_id, status)
    return archived
