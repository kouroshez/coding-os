"""core.web.routes.board — /api/board/* HTTP wrappers for cos_task_* tools.

Facade over four route modules (`_board_tasks`, `_board_views`, `_board_git`)
and two leaves (`_board_shared`, `_board_presence`, `_board_autospawn`).
Importing this module registers every board route on the shared router.
"""

from __future__ import annotations

from ._board_autospawn import (
    _AUTO_SPAWN_MAX_TURNS as _AUTO_SPAWN_MAX_TURNS,
    _AUTO_SPAWN_TIMEOUT_SECS as _AUTO_SPAWN_TIMEOUT_SECS,
    _auto_spawn_enabled as _auto_spawn_enabled,
    _auto_spawn_inflight as _auto_spawn_inflight,
    _auto_spawn_lock as _auto_spawn_lock,
    _auto_spawn_run as _auto_spawn_run,
    _auto_spawn_safe as _auto_spawn_safe,
)
from ._board_git import (
    _SHA_RE as _SHA_RE,
    _TASK_FILE_RE as _TASK_FILE_RE,
    _is_other_task_file as _is_other_task_file,
    _run_git as _run_git,
    board_commit as board_commit,
    board_diff as board_diff,
)
from ._board_presence import (
    _ACTIVE_WINDOW_SECS as _ACTIVE_WINDOW_SECS,
    _DB_FALLBACK_WINDOW_SECS as _DB_FALLBACK_WINDOW_SECS,
    _agent_active_from_db as _agent_active_from_db,
    _agent_state as _agent_state,
    _agent_state_fs as _agent_state_fs,
    _pid_alive as _pid_alive,
    _pid_alive_fn as _pid_alive_fn,
    _presence_dir as _presence_dir,
    _presence_files as _presence_files,
    _presence_state as _presence_state,
    _session_inventory as _session_inventory,
    _session_inventory_fs as _session_inventory_fs,
    _session_presence as _session_presence,
    _session_presence_fn as _session_presence_fn,
)
from ._board_shared import (
    _CORE_DIR as _CORE_DIR,
    _board_tools as _board_tools,
    _db_conn as _db_conn,
    _unavailable as _unavailable,
    logger as logger,
    router as router,
)
from ._board_tasks import (
    board_create as board_create,
    board_move as board_move,
    board_reposition as board_reposition,
    board_task_chat_ref as board_task_chat_ref,
    board_task_detail as board_task_detail,
    board_task_edit as board_task_edit,
    board_task_history as board_task_history,
    board_task_ready as board_task_ready,
)
from ._board_views import (
    board_config as board_config,
    board_daily as board_daily,
    board_list as board_list,
    board_pick as board_pick,
    board_retro as board_retro,
    board_wip as board_wip,
)

__all__ = [
    "board_commit",
    "board_config",
    "board_create",
    "board_daily",
    "board_diff",
    "board_list",
    "board_move",
    "board_pick",
    "board_reposition",
    "board_retro",
    "board_task_chat_ref",
    "board_task_detail",
    "board_task_edit",
    "board_task_history",
    "board_task_ready",
    "board_wip",
    "logger",
    "router",
]
