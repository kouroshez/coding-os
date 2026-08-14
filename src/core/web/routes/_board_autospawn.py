"""core.web.routes._board_autospawn — dispatch an implementer on a human icebox pull.

Gated by `hub-settings.json::auto_spawn.enabled` (default off) and deduped per
(project_root, task_id) so a double drag never stacks two sessions on one card.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from ._board_shared import _CORE_DIR, logger


def _auto_spawn_enabled() -> bool:
    try:
        from .settings import _load as _load_hub_settings

        return bool((_load_hub_settings().get("auto_spawn") or {}).get("enabled"))
    except Exception as exc:
        logger.debug("auto-spawn settings read failed: %s", exc)
        return False


_AUTO_SPAWN_TIMEOUT_SECS = 1800.0
_AUTO_SPAWN_MAX_TURNS = 100

# One spawn per task per hub process — a double drag (or a force retry)
# must not stack two implementer sessions on the same card.
_auto_spawn_inflight: set[str] = set()
_auto_spawn_lock = threading.Lock()


def _auto_spawn_run(task_id: str, project_root: str, db_path: str) -> None:
    import asyncio
    import secrets
    import time as _time

    session_id = f"ses-claude-autospawn-{int(_time.time())}-{secrets.token_hex(3)}"
    status = "error"
    error: str | None = None
    latency_ms = 0
    try:
        from thinking_os.dispatcher import DispatchRequest, get_dispatcher

        agent_file = _CORE_DIR / "core" / "thinking_os" / "agents" / "implementer.md"
        if not agent_file.is_file():
            agent_file = Path(_CORE_DIR) / "thinking_os" / "agents" / "implementer.md"
        request = DispatchRequest(
            formula_id="implementer",
            agent_file=str(agent_file),
            prompt=(
                f"A human pulled {task_id} from icebox to in_progress on the board and "
                "expects you to deliver it autonomously. Load the spec with "
                f"`cos task-show {task_id}`, bind the session with `cos task-start "
                f"{task_id}`, then run the Core Loop (Orient → Plan → Execute → Verify): "
                "implement the smallest change satisfying the Acceptance (G/W/T), run the "
                "Verification-Matrix command for what you changed, commit with explicit "
                f"paths, then `cos task-move {task_id} --to testing` and close with "
                f"`cos task-done {task_id}` only on a verified pass."
            ),
            intensity="full",
            timeout_s=_AUTO_SPAWN_TIMEOUT_SECS,
            session_id=session_id,
            cwd=project_root,
            max_turns=_AUTO_SPAWN_MAX_TURNS,
        )
        dispatcher = get_dispatcher(request=request)
        result = asyncio.run(dispatcher.dispatch(request))
        status = result.status if result.status in ("ok", "timeout", "error") else "error"
        error = result.error
        latency_ms = result.latency_ms
    except Exception as exc:
        error = str(exc)[:1000]
        logger.warning("auto-spawn dispatch failed for %s: %s", task_id, exc)
    finally:
        with _auto_spawn_lock:
            _auto_spawn_inflight.discard(f"{project_root}::{task_id}")

    # Record into formula_dispatches so the stream's `dispatch-completed`
    # event is the visible success/failure row for the spawn.
    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                "INSERT INTO formula_dispatches "
                "(session_id, task_marker, persona_id, formula_id, input_hash, "
                "output_hash, latency_ms, status, ts, error) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    session_id,
                    task_id,
                    "auto-spawn",
                    "implementer",
                    "",
                    "",
                    latency_ms,
                    status,
                    # Match the column default datetime('now'): UTC, space separator.
                    _time.strftime("%Y-%m-%d %H:%M:%S", _time.gmtime()),
                    error,
                ),
            )
    except Exception as exc:
        logger.debug("auto-spawn dispatch record failed: %s", exc)


def _auto_spawn_safe(
    task_id: str,
    previous_status: str | None,
    to: str,
    agent_session: str | None,
) -> None:
    # Human panel drags only — an agent-initiated move carries its own session.
    if to != "in_progress" or previous_status != "icebox":
        return
    if agent_session and agent_session != "human":
        return
    if not _auto_spawn_enabled():
        return
    from web._project_context import current_db_path, current_project_root

    # Key the dedup set by (project_root, task_id): task ids are per-project and
    # every project numbers, so a bare task_id would collide two
    # projects' cards in this one shared hub process.
    root = str(current_project_root())
    db_path = str(current_db_path())
    inflight_key = f"{root}::{task_id}"
    with _auto_spawn_lock:
        if inflight_key in _auto_spawn_inflight:
            logger.info("auto-spawn: %s already dispatching, skipped", task_id)
            return
        _auto_spawn_inflight.add(inflight_key)
    try:
        threading.Thread(target=_auto_spawn_run, args=(task_id, root, db_path), daemon=True).start()
        logger.info("auto-spawn: dispatching implementer on %s", task_id)
    except Exception as exc:
        with _auto_spawn_lock:
            _auto_spawn_inflight.discard(inflight_key)
        logger.warning("auto-spawn thread start failed for %s: %s", task_id, exc)
