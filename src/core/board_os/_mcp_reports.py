"""Private sibling of board_os.mcp_tools — import via the kernel, never directly.

Read-only board summaries: the daily standup, the retrospective and its
hook-block trend, and the WIP-cap health check.
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timezone

from board_os.workflow import (  # type: ignore[import-not-found]
    check_wip,
)
from thinking_os.tools._shared import fail, ok, safe_tool  # type: ignore[import-not-found]

from ._mcp_board import _keyset_column_page
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
from ._mcp_stranded import _archive_stale_sweep, cos_task_reclaim

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

    # Bounded standup queries: a 24h window or a runaway icebox must
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
        return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

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
