"""Record a closed task's outcome for metrics and model routing."""

from __future__ import annotations

import os
import sqlite3

from cli._board_cli_shared import _project_root

_KIND_TO_OUTCOME_TYPE = {
    "bug": "fix",
    "feature": "feat",
    "refactor": "refactor",
    "docs": "docs",
    "test": "test",
    "chore": "infra",
}

_brain_logger = __import__("logging").getLogger("cli.board.brain")


def _record_brain_outcome_safe(conn: sqlite3.Connection, task_id: str) -> None:
    """Fire-and-forget: record task-done in task_outcomes for metrics and routing.

    Any failure is logged at DEBUG — task-done must never surface a recording
    failure to the user.
    """
    try:
        from thinking_os.record_outcome import record_outcome

        row = conn.execute(
            "SELECT kind, title FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        kind = row[0] if row else "feature"
        msg = row[1] if row else ""
        task_type = _KIND_TO_OUTCOME_TYPE.get(kind, "feat")
        db_path = os.environ.get(
            "COS_DB_PATH",
            str(_project_root() / ".coding-os" / "coding-os.db"),
        )
        record_outcome(
            task_id=task_id,
            task_type=task_type,
            outcome="success",
            msg=msg,
            db_path=db_path,
        )
        # Stamp the model onto the fresh row so routing_weights has input.
        # COS_AGENT_MODEL is set by adapter startup; unknown → leave null.
        model = os.environ.get("COS_AGENT_MODEL") or os.environ.get("ANTHROPIC_MODEL")
        if model:
            try:
                conn.execute(
                    "UPDATE task_outcomes SET model = ? WHERE task_id = ? AND model IS NULL",
                    (model, task_id),
                )
                conn.commit()
            except Exception as exc:
                _brain_logger.debug("model stamp failed for %s: %s", task_id, exc)
    except Exception as exc:
        _brain_logger.debug("record_outcome failed for %s: %s", task_id, exc)
        return

    # Rebuild routing_weights every 10 outcomes so `cos_route_model` /
    # `cos_route_skill` have current empirical success rates. No-op until
    # task_outcomes has rows with non-null `model`.
    try:
        count = conn.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()[0]
        if count > 0 and count % 10 == 0:
            from thinking_os.tools.routing import recalculate_weights

            recalculate_weights(conn)
    except Exception as exc:
        _brain_logger.debug("recalculate_weights failed: %s", exc)
