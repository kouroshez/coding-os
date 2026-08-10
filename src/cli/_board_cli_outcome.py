"""Mirror a closed task into the thinking_os learning loop."""

from __future__ import annotations

import os
import sqlite3

import click

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
    """Fire-and-forget: mirror task-done into the thinking_os learning loop.

    Writes task_outcomes + outcome_history, back-fills retrievals.outcome for
    every row that cited this task, and triggers learn_extract each 10th
    successful outcome. Any failure is logged at DEBUG — task-done must never
    surface a brain-pipeline failure to the user.
    """
    derived_outcome = "success"  # refined below if record_outcome derives 'rework'
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
        _oc = record_outcome(
            task_id=task_id,
            task_type=task_type,
            outcome="success",
            msg=msg,
            db_path=db_path,
        )
        # record_outcome refines 'success' → 'rework' from task history; carry
        # that derived value to the retrievals back-fill below so it is not a
        # SECOND hardcoded-'success' writer (the exact bug class in this file).
        if isinstance(_oc, dict) and _oc.get("outcome"):
            derived_outcome = _oc["outcome"]
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

    # retrievals.task_id is composite ("<session_id> <task_slug>") in some
    # writers, plain TASK-NNN in others — match both shapes defensively.
    try:
        conn.execute(
            "UPDATE retrievals SET outcome = ?, outcome_at = CURRENT_TIMESTAMP "
            "WHERE outcome IS NULL AND (task_id = ? OR task_id LIKE ?)",
            (derived_outcome, task_id, f"%{task_id}%"),
        )
        conn.commit()
    except Exception as exc:
        _brain_logger.debug("retrieval back-fill failed for %s: %s", task_id, exc)

    try:
        count = conn.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()[0]
        if count > 0 and count % 10 == 0:
            from scheduled._activity import outcomes_since_marker
            from scheduled._state import state_dir, touch_marker
            from thinking_os.database import resolve_db_path
            from thinking_os.tools.learning import learn_extract

            # Respect the shared .last-extract marker so this every-10 path does
            # not double-extract with nightly / responsive (audit: it bypassed
            # the marker, breaking the shared idempotency contract).
            root = _project_root()
            marker = state_dir(root) / ".last-extract"
            # Only extract when there ARE outcomes since the last extract by ANY
            # path; skip silently otherwise (don't return — routing/doc rebuild
            # below must still run).
            if outcomes_since_marker(resolve_db_path(root), marker) > 0:
                result = learn_extract(conn)
                touch_marker(marker)
                extracted = result.get("extracted", [])
                if extracted:
                    click.echo(
                        f"\n🧠 Learning: {len(extracted)} new pattern(s) from {count} outcomes:",
                    )
                    for p in extracted:
                        click.echo(
                            f"   • {p.get('pattern')} (confidence: {p.get('confidence', 0):.2f})",
                        )
    except Exception as exc:
        _brain_logger.debug("learn_extract trigger failed: %s", exc)

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

    # Shift document_chunks.priority based on (retrieval, outcome) pairs
    # every 10 outcomes so docs that supported successful work get gently
    # boosted and failed ones decay.  Bounded by _DELTA_* constants inside
    # learn_from_retrievals; never cliff-jumps a single chunk.
    try:
        count = conn.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()[0]
        if count > 0 and count % 10 == 0:
            from thinking_os.tools.retrieve import learn_from_retrievals

            learn_from_retrievals(conn, lookback_days=14)
    except Exception as exc:
        _brain_logger.debug("learn_from_retrievals failed: %s", exc)

    # Sweep dangling embeddings + concept-graph edges + trash observations
    # every 10 outcomes. Cheap because NOT EXISTS / LIKE globs are indexed
    # and the row counts are small in practice.
    try:
        count = conn.execute("SELECT COUNT(*) FROM task_outcomes").fetchone()[0]
        if count > 0 and count % 10 == 0:
            from thinking_os.memory_gc import gc_memory

            _db_path = os.environ.get(
                "COS_DB_PATH",
                str(_project_root() / ".coding-os" / "coding-os.db"),
            )
            gc_memory(db_path=_db_path)
    except Exception as exc:
        _brain_logger.debug("gc_memory failed: %s", exc)
