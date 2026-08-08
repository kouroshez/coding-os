"""board_os MCP tools — `cos_task_*` surface.

Implements board MCP tools, including:
    cos_task_create, cos_task_board, cos_task_move, cos_task_reposition,
    cos_task_pick, cos_task_daily, cos_task_retro, cos_task_wip_check,
    cos_work_log_append

All tools use the shared ok()/fail()/@safe_tool envelope (Rule 14).
`core/thinking_os/server.py` imports this module and wraps each tool;
the implementation lives in the private _mcp_* siblings re-exported at
the bottom, so this module stays the single public + monkeypatch surface.

Stateless from the caller's perspective:
- Open one connection per call (via the server's connection factory),
- call the underlying board_os primitives (config.load_config,
  parser.parse_task, sync.sync_one, workflow.transition),
- shape the response into ok()/fail() with token-budgeted meta.
"""

# ---------------------------------------------------------------------------
# Split modules — mcp_tools stays the single public + monkeypatch surface;
# the implementation lives in private _mcp_* siblings (imported last so they
# can statically import the kernel helpers above).
# ---------------------------------------------------------------------------
from ._mcp_board import (  # noqa: F401
    _ACTIVE_COLUMN_HARD_MAX,
    _BOARD_BUDGET_HEADROOM,
    _BOARD_CURSOR_VERSION,
    _PAGE_SIZE_HARD_MAX,
    _PAGED_STATUSES,
    _cap_board_to_budget,
    _decode_board_cursor,
    _encode_board_cursor,
    _keyset_column_page,
    _keyset_filter,
    cos_task_board,
    cos_task_show,
)
from ._mcp_create import (  # noqa: F401
    _kind_outcome_placeholder,
    _next_steps_for_kind,
    _render_kind_aware_body,
    _render_lean_frontmatter,
    cos_task_create,
)
from ._mcp_history import (  # noqa: F401
    _WORKLOG_HEADING_RE,
    _git_commits_by_task_id,
    _git_commits_for_path,
    _git_commits_from_worklog,
    _record_task_edit,
    _strip_leading_h1,
    _worklog_events,
    _worklog_span,
    cos_task_edit,
    cos_task_history,
)
from ._mcp_lifecycle import (  # noqa: F401
    _TERMINAL_DEP_STATES,
    _auto_reclaim_zombies_safe,
    _cascade_ready_dependents_safe,
    _close_learning_loop_safe,
    _labels_list_from_json,
    _patch_labels_line,
    _ready_dor_check,
    _record_completion_outcome_safe,
    cascade_ready_dependents,
    cos_task_move,
    cos_task_ready,
    cos_task_reposition,
)
from ._mcp_reclaim import (  # noqa: F401
    _KEEP_LABELS,
    _PRIORITY_WEIGHT,
    _WORKLOG_SUMMARY_CAP,
    _active_session_ids,
    _archive_stale_sweep,
    _classify_stranded,
    _commits_referencing_batch,
    _has_work_log,
    _hook_block_trend,
    _reconcile_recommendation,
    _resolve_task_file,
    _truncate_summary,
    cos_task_claim_next,
    cos_task_daily,
    cos_task_pick,
    cos_task_reclaim,
    cos_task_reconcile,
    cos_task_retro,
    cos_task_wip_check,
    cos_work_log_append,
)
from ._mcp_shared import (  # noqa: F401
    _BOARD_SELECT,
    _COMMIT_SCAN_CAP,
    _COMPLETION_EVIDENCE_RE,
    _SLUG_RE,
    _STRANDED_SCAN_LIMIT,
    _TASK_ID_ALLOCATORS,
    APPETITE_RE,
    KIND_ENUM,
    PRIORITY_ENUM,
    READY_LABEL,
    STATUS_ENUM,
    SYSTEM_SESSION_PREFIX,
    TASK_ID_FORMAT_RE,
    TOKEN_BUDGET_CHARS,
    Path,
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
    check_wip,
    cos_task_link,
    datetime,
    dependents_of,
    fail,
    incomplete_dependencies,
    json,
    load_config,
    logger,
    logging,
    ok,
    os,
    parse_task,
    patch_task_frontmatter_scalars,
    re,
    safe_tool,
    sqlite3,
    sync_one,
    time,
    transition,
    validate_dependencies_no_cycle,
)
