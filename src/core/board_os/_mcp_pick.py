"""Private sibling of board_os.mcp_tools — import via the kernel, never directly.

What to work on next: the priority-weighted candidate ranking and the atomic
claim that binds the top candidate to a session.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from board_os.workflow import (  # type: ignore[import-not-found]
    _has_task_dependencies_table,
    transition,
)
from thinking_os.tools._shared import fail, ok, safe_tool  # type: ignore[import-not-found]

from ._mcp_board import cos_task_show
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
