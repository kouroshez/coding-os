"""cos board-* CLI commands.

Commands:
    cos board [--web] [--port N] [--swimlane] [--kind] [--epic] [--priority]
    cos task-create
    cos task-move
    cos task-start / task-done / task-block / task-cancel
    cos task-pick
    cos task-archive
    cos daily / retro
    cos task-show / task-log / task-history / wip
    cos task-validate
    cos board-config --init

Thin click wrappers over core.board_os.{mcp_tools,workflow,parser,sync}.
All commands use the project's SQLite DB (.coding-os/coding-os.db)
unless COS_DB_PATH overrides.
"""

from __future__ import annotations

import sys

import click

from cli._board_cli_lifecycle import (
    task_archive_cmd,
    task_block_cmd,
    task_cancel_cmd,
    task_create_cmd,
    task_done_cmd,
    task_move_cmd,
    task_ready_cmd,
    task_reclaim_cmd,
    task_reconcile_cmd,
    task_start_cmd,
)
from cli._board_cli_outcome import (  # pre-split re-export
    _record_brain_outcome_safe as _record_brain_outcome_safe,
)
from cli._board_cli_shared import (  # pre-split re-export
    _agent_session_id as _agent_session_id,
    _db_conn as _db_conn,
    _detect_agent_runtime as _detect_agent_runtime,
    _known_agent_ids as _known_agent_ids,
    _parse_envelope as _parse_envelope,
    _print_envelope as _print_envelope,
    _project_root as _project_root,
)
from cli._board_cli_validate import board_config_cmd, task_validate_cmd
from cli._board_cli_views import (
    board_cmd,
    daily_cmd,
    retro_cmd,
    task_history_cmd,
    task_log_cmd,
    task_pick_cmd,
    task_show_cmd,
    wip_cmd,
)


# ---------------------------------------------------------------------------
@click.command(
    "task-link",
    help="Link a task to a forge issue/PR — sets external_ref (e.g. github#42). "
    "Forge auto-detected from origin. REF accepts 42, github#42, or an issue URL.",
)
@click.argument("task_id")
@click.argument("ref")
def task_link_cmd(task_id, ref):
    from board_os import mcp_tools

    conn = _db_conn()
    try:
        envelope = mcp_tools.cos_task_link(conn, task_id=task_id, ref=ref)
    finally:
        conn.close()
    sys.exit(_print_envelope(envelope))


# ---------------------------------------------------------------------------
# Commands bundle — register via cli.add_command(each)
# ---------------------------------------------------------------------------

BOARD_COMMANDS = [
    task_link_cmd,
    board_cmd,
    task_create_cmd,
    task_move_cmd,
    task_start_cmd,
    task_ready_cmd,
    task_reclaim_cmd,
    task_reconcile_cmd,
    task_done_cmd,
    task_block_cmd,
    task_cancel_cmd,
    task_archive_cmd,
    task_pick_cmd,
    daily_cmd,
    retro_cmd,
    wip_cmd,
    task_show_cmd,
    task_log_cmd,
    task_history_cmd,
    task_validate_cmd,
    board_config_cmd,
]
