"""Private sibling of board_os.mcp_tools — import via the kernel, never directly."""

from __future__ import annotations

import base64
import json
import sqlite3

from board_os.workflow import (
    check_wip,
)
from thinking_os.tools._shared import TOKEN_BUDGET_CHARS, _budget_size, fail, ok, safe_tool

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

_BOARD_BUDGET_HEADROOM = 256


def _cap_board_to_budget(cards: list[dict], *, budget: int) -> tuple[list[dict], bool]:
    # Drop the lowest-priority cards (P9 last) until the serialized board body
    # fits `budget` (agent path only — the browser opts out via apply_budget=False).
    # The kept set preserves original display order. `cards` is outside the
    # envelope trim ladder, so without this cap a large board produced an
    # unshrinkable >32KB envelope (TASK-209). Returns (kept, capped). The board no
    # longer emits a duplicate `grouped` view (TASK-259) — clients group cards by
    # swimlane×status themselves, halving the payload on both the agent and wire.
    def _fits(subset: list[dict]) -> bool:
        # Mirror ok(): pretty-printed full envelope, measured with the same
        # _budget_size the trimmer uses (inflates non-Latin), so the cap holds
        # for Persian/Arabic titles too — not just ASCII.
        probe = json.dumps(
            {
                "ok": True,
                "data": {
                    "cards": subset,
                    "count": len(subset),
                    "total_count": len(cards),
                    "truncated": True,
                    "wip": {"counts": {}, "caps": {}, "violations": []},
                    "meta": {
                        "layer": "tasks",
                        "source": "board_os.cos_task_board",
                        "tokens_estimated": 0,
                        "truncated": True,
                    },
                },
            },
            indent=2,
            default=str,
        )
        return _budget_size(probe) <= budget

    if _fits(cards):
        return cards, False

    total = len(cards)
    ranked = sorted(range(total), key=lambda i: (str(cards[i].get("priority", "P9")), i))
    keep = total
    while keep > 0:
        keep = keep - 1 if keep <= 12 else int(keep * 0.85)
        keep_idx = set(ranked[:keep])
        subset = [c for i, c in enumerate(cards) if i in keep_idx]
        if _fits(subset):
            return subset, True
    return [], True


# Columns whose row count grows without bound (finished work accumulates
# forever). These are keyset-paginated; every other column is "active" and
# returned in full up to a safety cap. TASK-223.
_PAGED_STATUSES = ("complete", "archive")
# Safety cap on each active board read so even a runaway icebox can't OOM the
# response. Honest truncation is signalled via columns["_active"].
_ACTIVE_COLUMN_HARD_MAX = 2000
# Hard ceiling on one keyset page of a paged column.
_PAGE_SIZE_HARD_MAX = 200


# Cursor schema version — bump when the keyset key changes. A versioned
# cursor from an older schema decodes to None (page 1) instead of silently
# slicing the wrong key (TASK-399).
_BOARD_CURSOR_VERSION = "v1"


def _encode_board_cursor(completed_at: int | None, task_id: str) -> str:
    raw = json.dumps([_BOARD_CURSOR_VERSION, completed_at, task_id]).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_board_cursor(cursor: str | None) -> tuple[int | None, str] | None:
    if not cursor:
        return None
    try:
        version, completed_at, task_id = json.loads(
            base64.urlsafe_b64decode(cursor.encode("ascii"))
        )
        if version != _BOARD_CURSOR_VERSION:
            return None
        return completed_at, str(task_id)
    except Exception:
        return None


def _keyset_filter(cursor: str | None) -> tuple[str, list]:
    # Rows strictly AFTER the cursor in (completed_at DESC, task_id DESC) order;
    # NULL completed_at (archive rows) sort last.
    decoded = _decode_board_cursor(cursor)
    if decoded is None:
        return "", []
    completed_at, task_id = decoded
    if completed_at is None:
        # Inside the NULL-completed tail (archive): tiebreak by task_id only.
        return "completed_at IS NULL AND task_id < ?", [task_id]
    # Lower completed_at, or same completed_at + lower task_id, or the NULL tail.
    return (
        "(completed_at < ? OR (completed_at = ? AND task_id < ?) OR completed_at IS NULL)",
        [completed_at, completed_at, task_id],
    )


def _keyset_column_page(
    conn: sqlite3.Connection,
    status: str,
    base_clauses: list[str],
    base_params: list,
    cursor: str | None,
    page_size: int,
    config,
) -> tuple[list[dict], str | None, int]:
    page_size = max(1, min(int(page_size), _PAGE_SIZE_HARD_MAX))
    col_clauses = [*list(base_clauses), "status = ?"]
    col_params = [*list(base_params), status]

    total = conn.execute(
        f"SELECT COUNT(*) FROM tasks WHERE {' AND '.join(col_clauses)}", col_params
    ).fetchone()[0]

    ks_clause, ks_params = _keyset_filter(cursor)
    where = " AND ".join(col_clauses + ([ks_clause] if ks_clause else []))
    query = f"{_BOARD_SELECT} WHERE {where} ORDER BY completed_at DESC, task_id DESC LIMIT ?"
    rows = conn.execute(query, col_params + ks_params + [page_size + 1]).fetchall()
    has_more = len(rows) > page_size
    rows = rows[:page_size]
    cards = [_flag_stale(_task_card(r), config) for r in rows]

    next_cursor = None
    if has_more and cards:
        # Read the keyset key from the shaped card (named fields) instead of
        # positional row indexes — a _BOARD_SELECT column shuffle can no
        # longer silently corrupt pagination.
        last = cards[-1]
        next_cursor = _encode_board_cursor(last.get("completed_at"), last["id"])
    return cards, next_cursor, total


@safe_tool
def cos_task_board(
    conn: sqlite3.Connection,
    *,
    swimlane: str | None = None,
    kind: str | None = None,
    epic: str | None = None,
    status_filter: list[str] | None = None,
    include_archive: bool = False,
    limit: int = 50,
    page_size: int = 50,
    cursor: str | None = None,
    apply_budget: bool = True,
) -> str:
    config = _current_config()

    base_clauses: list[str] = []
    base_params: list = []
    for col, val in (("swimlane", swimlane), ("kind", kind), ("epic", epic)):
        if val:
            base_clauses.append(f"{col} = ?")
            base_params.append(val)

    # Split requested columns into ACTIVE (returned in full, capped) and PAGED
    # (complete/archive — keyset-paginated so a 50K-deep column never floods the
    # payload). Supersedes the interim apply_budget return-all (TASK-220/223).
    paged_set = set(_PAGED_STATUSES)
    if status_filter:
        active_statuses = [s for s in status_filter if s not in paged_set]
        paged_statuses = [s for s in status_filter if s in paged_set]
        want_active = bool(active_statuses)
    else:
        active_statuses = None  # all non-paged statuses, single query
        paged_statuses = list(_PAGED_STATUSES) if include_archive else []
        want_active = True

    columns_meta: dict = {}
    cards: list[dict] = []

    # ---- Active columns: full, bounded by a safety cap ----
    if want_active:
        active_cap = max(1, min(int(limit), _ACTIVE_COLUMN_HARD_MAX))
        a_clauses = list(base_clauses)
        a_params = list(base_params)
        if active_statuses:
            ph = ",".join("?" for _ in active_statuses)
            a_clauses.append(f"status IN ({ph})")
            a_params.extend(active_statuses)
        else:
            a_clauses.append("status NOT IN ('complete', 'archive')")
        where = f"WHERE {' AND '.join(a_clauses)}" if a_clauses else ""
        query = f"{_BOARD_SELECT} {where} ORDER BY swimlane, status, priority LIMIT ?"
        a_rows = conn.execute(query, [*a_params, active_cap + 1]).fetchall()
        active_truncated = len(a_rows) > active_cap
        a_rows = a_rows[:active_cap]
        cards.extend(_flag_stale(_task_card(r), config) for r in a_rows)
        if active_truncated:
            columns_meta["_active"] = {"truncated": True, "cap": active_cap}

    # ---- Paged columns: one keyset page each (cursor + per-column total) ----
    for status in paged_statuses:
        page_cards, next_cursor, col_total = _keyset_column_page(
            conn, status, base_clauses, base_params, cursor, page_size, config
        )
        cards.extend(page_cards)
        columns_meta[status] = {
            "total_count": col_total,
            "returned": len(page_cards),
            "next_cursor": next_cursor,
            "truncated": next_cursor is not None,
        }

    # Per-column queries make the payload inherently bounded. apply_budget still
    # applies the 32KB agent-context cap (a board read must never flood an
    # agent's context); the browser passes apply_budget=False and is safe now
    # that no single column returns more than its cap/page.
    total_count = len(cards)
    if apply_budget:
        # Account for the columns meta (not in _cap_board_to_budget's probe) so
        # the 32KB agent-envelope guarantee (TASK-209) holds even with paging.
        columns_overhead = len(json.dumps(columns_meta, default=str)) if columns_meta else 0
        cards, board_truncated = _cap_board_to_budget(
            cards, budget=TOKEN_BUDGET_CHARS - _BOARD_BUDGET_HEADROOM - columns_overhead
        )
    else:
        board_truncated = False

    wip_state = None
    if config is not None:
        state = check_wip(conn, config)
        wip_state = {
            "counts": state.counts,
            "caps": state.caps,
            "violations": list(state.violations),
        }

    return ok(
        {
            "cards": cards,
            "columns": columns_meta,
            "count": len(cards),
            "total_count": total_count,
            "truncated": board_truncated,
            "wip": wip_state,
        },
        meta={"layer": "tasks", "source": "board_os.cos_task_board"},
        # Browser path (apply_budget=False) opts out of the 32KB agent cap in
        # ok() too — not just _cap_board_to_budget above — so a large board never
        # trips envelope_unshrinkable on the wire. The agent path keeps the cap.
        apply_budget=apply_budget,
    )


# ---------- cos_task_show ----------


@safe_tool
def cos_task_show(
    conn: sqlite3.Connection,
    *,
    task_id: str,
    include_body: bool = True,
) -> str:
    row = conn.execute(
        "SELECT task_id, title, status, swimlane, kind, priority, appetite, "
        "file_path, epic, labels_json, agent_session, started_at, completed_at "
        "FROM tasks WHERE task_id = ?",
        (task_id,),
    ).fetchone()
    if row is None:
        return fail("not_found", f"task {task_id} not found")
    try:
        labels = json.loads(row[9] or "[]")
    except (TypeError, json.JSONDecodeError):
        labels = []
    data = {
        "id": row[0],
        "title": row[1],
        "status": row[2],
        "swimlane": row[3],
        "kind": row[4],
        "priority": row[5],
        "appetite": row[6],
        "file_path": row[7],
        # Fields the DB already stores but the tool used to drop, forcing callers
        # to re-parse the raw body. depends_on/blocked_by/references stay
        # frontmatter-only and remain available in `body`.
        "epic": row[8],
        "labels": labels,
        "agent_session": row[10],
        "started_at": row[11],
        "completed_at": row[12],
        "body": None,
    }
    if include_body and row[7]:
        full = _project_root() / row[7]
        if full.exists():
            data["body"] = full.read_text(encoding="utf-8")
    return ok(data, meta={"layer": "tasks", "source": "board_os.cos_task_show"})


# ---------- cos_task_move ----------
