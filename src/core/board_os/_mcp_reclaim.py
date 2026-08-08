"""Private sibling of board_os.mcp_tools — import via the kernel, never directly."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from board_os._agent_runtime import SYSTEM_SESSION_PREFIX
from board_os.config import (
    READY_LABEL,
)
from board_os.sync import sync_one
from board_os.workflow import (
    _has_task_dependencies_table,
    check_wip,
    transition,
)
from thinking_os.tools._shared import fail, ok, safe_tool

from ._mcp_board import _keyset_column_page, cos_task_show
from ._mcp_history import _WORKLOG_HEADING_RE
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
    # subprocesses, each O(history) at 1M commits). TASK-227.
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
    # per row. TASK-227.
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


# ---------- cos_task_pick ----------


_PRIORITY_WEIGHT = {"P0": 100, "P1": 50, "P2": 20, "P3": 5}


@safe_tool
def cos_task_pick(
    conn: sqlite3.Connection,
    *,
    swimlane: str | None = None,
    priority_min: str = "P2",
    max_candidates: int = 5,
) -> str:
    pm_weight = _PRIORITY_WEIGHT.get(priority_min, 20)
    # "ready" is no longer a column — candidates now live in icebox with
    # a 'ready' label, plus the emergency column.  LIKE on labels_json
    # is cheap (<200 chars) and avoids a JSON1 dependency.
    #
    # Dependency filter: a ready icebox card with any prerequisite that is not
    # `complete` isn't runnable now, so it's excluded via NOT EXISTS over the
    # indexed task_dependencies junction (a missing dep row — never synced —
    # has no status and counts as incomplete). emergency cards are unaffected.
    # Guarded on the junction existing so a pre-v35 DB still returns candidates.
    if _has_task_dependencies_table(conn):
        ready_clause = (
            "(status = 'icebox' AND labels_json LIKE '%\"ready\"%' "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM task_dependencies d "
            "  LEFT JOIN tasks dep ON dep.task_id = d.depends_on "
            "  WHERE d.task_id = tasks.task_id "
            "    AND (dep.status IS NULL OR dep.status != 'complete')))"
        )
    else:
        ready_clause = "(status = 'icebox' AND labels_json LIKE '%\"ready\"%')"
    clauses = [f"(status = 'emergency' OR {ready_clause})"]
    params: list = []
    if swimlane:
        clauses.append("swimlane = ?")
        params.append(swimlane)
    # Bounded: highest-priority candidates first, capped — pick only needs the
    # top max_candidates, and the cap keeps a 10K-ready icebox from a full load.
    query = f"{_BOARD_SELECT} WHERE {' AND '.join(clauses)} ORDER BY priority LIMIT 1000"
    rows = conn.execute(query, params).fetchall()

    scored: list[tuple[int, dict]] = []
    for row in rows:
        card = _task_card(row)
        p = _PRIORITY_WEIGHT.get(card["priority"], 0)
        if p < pm_weight:
            continue
        score = p + (30 if card["status"] == "emergency" else 0)
        scored.append((score, card))

    scored.sort(key=lambda x: -x[0])
    top = [c for _, c in scored[:max_candidates]]
    return ok(
        {"candidates": top, "count": len(top)},
        meta={"layer": "tasks", "source": "board_os.cos_task_pick"},
    )


# ---------- cos_task_claim_next ----------


@safe_tool
def cos_task_claim_next(
    conn: sqlite3.Connection,
    *,
    swimlane: str | None = None,
    priority_min: str = "P2",
    agent_session: str | None = None,
) -> str:
    """Atomically claim the highest-priority runnable task for this session.

    Select + claim in ONE step so N racing sessions each get a DISTINCT task or
    ``{claimed: null}`` — never the same task twice, never an exception. Reuses
    cos_task_pick (dependency-filtered, priority-ordered) for candidates, then
    walks them attempting an atomic ``→ in_progress`` move: transition's
    BEGIN IMMEDIATE + CAS ``WHERE status = <expected>`` lets exactly one session
    win each row; a loser's CAS-miss (category `transient`) is skipped to the
    next candidate. A per-session WIP-cap rejection stops the walk — this session
    is already at its focus limit — and returns ``{claimed: null}``.
    """
    agent_session = _resolve_attribution(agent_session)
    config = _current_config()

    # A wider window than max_candidates: under contention the top few rows may
    # all be claimed by peers before this session wins one, so scan deeper.
    pick_env = json.loads(
        cos_task_pick(conn, swimlane=swimlane, priority_min=priority_min, max_candidates=50)
    )
    if not pick_env.get("ok"):
        return fail("internal", "claim-next could not enumerate candidates")
    candidates = pick_env["data"]["candidates"]

    for card in candidates:
        expected_from = card["status"]  # 'icebox' (ready) or 'emergency'
        result = transition(
            conn,
            card["id"],
            "in_progress",
            reason="claim-next",
            agent_session=agent_session,
            expected_from=expected_from,
            config=config,
            file_path=_resolve_task_file(conn, card["id"]),
        )
        if result.ok:
            claimed = json.loads(cos_task_show(conn, task_id=card["id"]))
            return ok(
                {"claimed": claimed.get("data") if claimed.get("ok") else {"id": card["id"]}},
                meta={"layer": "tasks", "source": "board_os.cos_task_claim_next"},
            )
        # A peer beat us to this row (CAS miss / status changed) — try the next.
        if result.error_category == "transient":
            continue
        # WIP cap or a hard gate: this session can't take on more work now.
        break

    return ok(
        {"claimed": None},
        meta={"layer": "tasks", "source": "board_os.cos_task_claim_next"},
    )


def _resolve_task_file(conn: sqlite3.Connection, task_id: str) -> Path | None:
    row = conn.execute("SELECT file_path FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
    if not row or not row[0]:
        return None
    candidate = _project_root() / row[0]
    return candidate if candidate.exists() else None


# ---------- cos_task_daily ----------


@safe_tool
def cos_task_daily(
    conn: sqlite3.Connection,
    *,
    since: str = "24h",
    agent_session: str | None = None,
) -> str:
    hours = _parse_since(since)
    threshold = int(time.time() - hours * 3600)

    # Self-heal at the session-start ritual: reclaim zombie in_progress
    # tasks (idle + owner session inactive) before reporting state.
    # Fire-and-forget — daily must never fail on the reclaim path.
    config = _current_config()

    reclaimed: list[dict] = []
    try:
        rec_env = json.loads(cos_task_reclaim(conn, agent_session=agent_session))
        if rec_env.get("ok"):
            reclaimed = rec_env["data"]["reclaimed"]
    except Exception as exc:
        logger.debug("daily reclaim skipped: %s", exc)

    # Icebox outflow — auto-archive aged backlog/complete cards when the project
    # opted in (default off). Runs before the status queries so archived cards
    # drop out of the report naturally. Fire-and-forget.
    auto_archived: list[dict] = []
    try:
        auto_archived = _archive_stale_sweep(conn, config)
    except Exception as exc:
        logger.debug("daily archive sweep skipped: %s", exc)

    # Bounded standup queries (TASK-227): a 24h window or a runaway icebox must
    # not fetchall unboundedly. Active columns are WIP-small; icebox uses an
    # accurate COUNT + a bounded oldest-first sample for the stale preview.
    # Standup highlights only — most-recent N transitions, not the full window
    # (an unbounded list both OOMs at scale and blows the 32KB agent envelope).
    recent = conn.execute(
        "SELECT task_id, old_status, new_status, reason, transitioned_at "
        "FROM task_status_history "
        "WHERE transitioned_at >= ? "
        "ORDER BY transitioned_at DESC LIMIT 50",
        (threshold,),
    ).fetchall()

    in_progress = conn.execute(
        f"{_BOARD_SELECT} WHERE status = 'in_progress' ORDER BY priority LIMIT 200"
    ).fetchall()
    # `testing` was previously absent from daily — the protocol funnels work
    # there before completion, so an abandoned card most often rots in testing
    # (RC3). Report it so a stranded testing zombie is visible at standup.
    testing = conn.execute(
        f"{_BOARD_SELECT} WHERE status = 'testing' ORDER BY priority LIMIT 200"
    ).fetchall()
    blocked = conn.execute(
        f"{_BOARD_SELECT} WHERE status = 'blocked' ORDER BY priority LIMIT 200"
    ).fetchall()
    icebox_total = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'icebox'").fetchone()[0]
    icebox = conn.execute(
        f"{_BOARD_SELECT} WHERE status = 'icebox' ORDER BY last_transition_at ASC LIMIT 500"
    ).fetchall()

    wip = None
    if config is not None:
        state = check_wip(conn, config)
        wip = {"counts": state.counts, "caps": state.caps}

    in_progress_cards = [_flag_stale(_task_card(r), config) for r in in_progress]
    testing_cards = [_flag_stale(_task_card(r), config) for r in testing]
    blocker_cards = [_flag_stale(_task_card(r), config) for r in blocked]
    icebox_cards = [_flag_stale(_task_card(r), config) for r in icebox]
    icebox_stale = [c for c in icebox_cards if c.get("stale")]
    icebox_summary = {
        "total": icebox_total,  # accurate count; cards below are a bounded sample
        "stale": len(icebox_stale),
        "stale_ids": [c["id"] for c in icebox_stale[:20]],
    }

    return ok(
        {
            "yesterday": [
                {
                    "task_id": r[0],
                    "old_status": r[1],
                    "new_status": r[2],
                    "reason": r[3],
                    "transitioned_at": r[4],
                }
                for r in recent
            ],
            "in_progress": in_progress_cards,
            "testing": testing_cards,
            "blockers": blocker_cards,
            "icebox": icebox_summary,
            "wip": wip,
            "reclaimed": reclaimed,
            "auto_archived": auto_archived,
        },
        meta={"layer": "tasks", "source": "board_os.cos_task_daily"},
    )


# ---------- cos_task_retro ----------


@safe_tool
def _hook_block_trend(conn: sqlite3.Connection, threshold: int, hours: float) -> dict | None:
    # Hook BLOCKs are mirrored into log_events (scope 'hook.<name>', kv
    # action=block) by cos_log_hook's durable sink — no new capture needed.
    # A falling blocks/session rate is the KPI that rules are being
    # internalized; both windows empty -> None keeps the retro noise-free.
    if not _has_table(conn, "log_events"):
        return None

    def iso_utc(epoch: int) -> str:
        return datetime.utcfromtimestamp(epoch).strftime("%Y-%m-%dT%H:%M:%SZ")

    def window(start: int, end: int) -> tuple[int, int, dict[str, int]]:
        rows = conn.execute(
            "SELECT scope, COALESCE(session_id, '') FROM log_events "
            "WHERE scope LIKE 'hook.%' AND kv LIKE ? "
            "AND created_at >= ? AND created_at < ?",
            ('%"action": "block"%', iso_utc(start), iso_utc(end)),
        ).fetchall()
        by_hook: dict[str, int] = {}
        sessions: set[str] = set()
        for scope, session in rows:
            hook = scope.removeprefix("hook.")
            by_hook[hook] = by_hook.get(hook, 0) + 1
            if session:
                sessions.add(session)
        return len(rows), len(sessions), by_hook

    now = int(time.time())
    span = int(hours * 3600)
    blocks, session_count, by_hook = window(threshold, now)
    prev_blocks, prev_session_count, _ = window(threshold - span, threshold)
    if blocks == 0 and prev_blocks == 0:
        return None
    rate = round(blocks / max(1, session_count), 2)
    prev_rate = round(prev_blocks / max(1, prev_session_count), 2)
    if rate < prev_rate:
        trend = "improving"
    elif rate > prev_rate:
        trend = "worsening"
    else:
        trend = "flat"
    top = sorted(by_hook.items(), key=lambda item: -item[1])[:5]
    return {
        "blocks": blocks,
        "sessions": session_count,
        "blocks_per_session": rate,
        "previous_blocks_per_session": prev_rate,
        "trend": trend,
        "top_hooks": [{"hook": hook, "blocks": count} for hook, count in top],
    }


def cos_task_retro(
    conn: sqlite3.Connection,
    *,
    since: str = "7d",
    page_size: int = 25,
    cursor: str = "",
) -> str:
    hours = _parse_since(since)
    threshold = int(time.time() - hours * 3600)

    # Aggregates over the WHOLE window via a slim projection — serializing
    # every full card blew the 32k envelope budget at ~270 completions
    # (observed 178k, envelope_unshrinkable).
    window_rows = conn.execute(
        "SELECT swimlane, started_at, completed_at FROM tasks "
        "WHERE status = 'complete' AND completed_at >= ?",
        (threshold,),
    ).fetchall()

    cycle_times_min = [
        (done - started) / 60.0 for _, started, done in window_rows if started and done
    ]
    avg_cycle = (sum(cycle_times_min) / len(cycle_times_min)) if cycle_times_min else None

    per_lane: dict[str, int] = {}
    for lane, _, _ in window_rows:
        per_lane[lane or "(none)"] = per_lane.get(lane or "(none)", 0) + 1

    emergency_count = conn.execute(
        "SELECT COUNT(*) FROM task_status_history "
        "WHERE new_status = 'emergency' AND transitioned_at >= ?",
        (threshold,),
    ).fetchone()[0]

    # Highlights page — same keyset machinery as the board's complete column,
    # trimmed to digest fields (the long tail rides the cursor).
    cards, next_cursor, total = _keyset_column_page(
        conn,
        "complete",
        ["completed_at >= ?"],
        [threshold],
        cursor or None,
        page_size,
        _current_config(),
    )
    digest_fields = ("id", "title", "swimlane", "kind", "priority", "completed_at")
    completed = [{k: c.get(k) for k in digest_fields} for c in cards]

    payload = {
        "completed": completed,
        "completed_count": total,
        "cycle_time_avg_minutes": avg_cycle,
        "emergency_count": emergency_count,
        "swimlane_throughput": per_lane,
        "next_cursor": next_cursor,
    }
    block_trend = _hook_block_trend(conn, threshold, hours)
    if block_trend is not None:
        payload["hook_block_trend"] = block_trend
    return ok(
        payload,
        meta={
            "layer": "tasks",
            "source": "board_os.cos_task_retro",
            "truncated": bool(next_cursor),
        },
    )


# ---------- cos_task_wip_check ----------


@safe_tool
def cos_task_wip_check(conn: sqlite3.Connection) -> str:
    config = _current_config()
    if config is None:
        return fail(
            "unavailable",
            "scrumban-config.yaml not found — run `cos board-config --init`",
        )
    state = check_wip(conn, config)
    return ok(
        {
            "counts": state.counts,
            "caps": state.caps,
            "violations": list(state.violations),
            "over_cap": bool(state.violations),
        },
        meta={"layer": "tasks", "source": "board_os.cos_task_wip_check"},
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

    date = datetime.utcnow().strftime("%Y-%m-%d")
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


# ---------- cos_task_history ----------
