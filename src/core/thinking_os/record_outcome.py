#!/usr/bin/env python3
"""
Thinking OS — Record task outcome to task_outcomes table (TASK-136).

Called by `cos task-done` (src/cli/board_commands.py) as a fire-and-forget step.
Writes to coding-os.db if it exists, exits silently otherwise.

Usage:
    python record_outcome.py --task TASK-140 --type feat --outcome success --msg "summary"
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from database import DEFAULT_DB_PATH, get_connection

from core.logging_os import setup as _logging_os_setup

_logging_os_setup(level="info")
logger = logging.getLogger("thinking_os.outcome")

VALID_OUTCOMES = {"success", "rework", "partial", "blocked"}


def _state_search_dirs() -> list[str]:
    # Dirs to search for a per-panel/per-agent state marker, most-specific
    # first: panel dir -> agent dir -> <state>/<agent> -> state dir. The
    # long-lived MCP server has no COS_PANEL_DIR/COS_AGENT_DIR but does know
    # COS_AGENT, so the <state>/<agent> entry is what makes markers resolvable
    # there (proven: skills_used captures via this path, model/gate did not).
    state_dir = os.environ.get("COS_STATE_DIR", ".coding-os")
    agent = os.environ.get("COS_AGENT", "")
    dirs = [d for d in (os.environ.get("COS_PANEL_DIR"), os.environ.get("COS_AGENT_DIR")) if d]
    if agent:
        dirs.append(str(Path(state_dir) / agent))
    dirs.append(state_dir)
    return dirs


def _read_gate_file() -> tuple[str, int]:
    """Read complexity classification from the .thinking_os-gate marker.

    The gate is per-panel (it is in COS_PER_PANEL_FILES), so search the panel dir
    first, then the agent dir, then <state>/<agent>, then COS_STATE_DIR — the same
    order _read_active_skills uses. Reading COS_STATE_DIR alone left complexity
    UNKNOWN on every panel-scoped completion (audit B-4: routing-loop starvation).
    Format: "<session-or-panel-id> <CLASSIFICATION> <N>"; the id prefix is skipped.
    """
    gate_path = None
    for d in _state_search_dirs():
        candidate = Path(d) / ".thinking_os-gate"
        if candidate.exists():
            gate_path = candidate
            break
    if gate_path is None:
        return "UNKNOWN", 1
    try:
        content = gate_path.read_text().strip()
        parts = content.split()
        # Skip a leading session/panel-id token. The writer prefixes the value
        # with the panel session id (ses-…) or, before one exists, the panel
        # ppid hash (ppid-…) — the gate parser only stripped "ses-" and so read
        # "ppid-…" as the complexity. Legacy format ("COMPLICATED 4") has none.
        if parts and parts[0].startswith(("ses-", "ppid-", "c-sess", "anon")):
            parts = parts[1:]
        complexity = parts[0] if parts else "UNKNOWN"
        dimensions = int(parts[1]) if len(parts) > 1 else 1
        return complexity, dimensions
    except (ValueError, IndexError):
        return "UNKNOWN", 1


def _detect_domain(task_id: str, msg: str) -> str:
    """Infer domain from task content."""
    import re

    text = f"{task_id} {msg}"
    # Use word boundaries to avoid false positives (e.g. "bUIld" matching "UI")
    if re.search(r"\b(BACKEND|Django|DRF|API|models?\.py)\b", text, re.IGNORECASE):
        return "BACKEND"
    if re.search(r"\b(FRONTEND|React|Next\.?js|component|CSS|Tailwind)\b", text, re.IGNORECASE):
        return "FRONTEND"
    if re.search(r"\b(DOCS?|README|governance|content)\b", text, re.IGNORECASE):
        return "DOCS"
    return "INFRA"


def _current_session() -> str:
    f = os.environ.get("COS_SESSION_FILE")
    if f and Path(f).exists():
        return Path(f).read_text().strip()
    for d in (os.environ.get("COS_PANEL_DIR"), os.environ.get("COS_AGENT_DIR")):
        if d and (Path(d) / "session-id").exists():
            return (Path(d) / "session-id").read_text().strip()
    return ""


def _read_active_skills() -> str | None:
    sid = _current_session()
    state_dir = Path(os.environ.get("COS_STATE_DIR", ".coding-os"))
    paths = [
        Path(d) / ".active-skill"
        for d in (os.environ.get("COS_PANEL_DIR"), os.environ.get("COS_AGENT_DIR"))
        if d
    ]
    agent = os.environ.get("COS_AGENT", "")
    if agent:
        paths.append(state_dir / agent / ".active-skill")
    paths.append(state_dir / ".active-skill")
    for p in paths:
        try:
            if not p.exists():
                continue
            parts = p.read_text().strip().split()
            # Strip a leading session/panel-id token (exact match, or the
            # ppid-/ses-/c-sess/anon/hex-id shapes) so skills_used groups
            # cleanly for skill_correlation mining.
            if parts and (parts[0] == sid or re.match(r"^(ppid-|ses-|c-sess|anon)", parts[0])):
                parts = parts[
                    1:
                ]  # explicit prefixes only — a bare-hex match could strip a real skill name
            if parts:
                return " ".join(parts)
        except OSError:
            continue
    return None


def _resolve_model() -> str | None:
    model = os.environ.get("COS_AGENT_MODEL") or os.environ.get("ANTHROPIC_MODEL")
    if model:
        return model
    # The model snapshot lives at <state>/<agent>/.model — _state_search_dirs
    # adds that path so the MCP server (no COS_AGENT_DIR) resolves it; before,
    # task_outcomes.model was NULL on every MCP-driven completion.
    for d in _state_search_dirs():
        try:
            marker = Path(d) / ".model"
            if marker.exists():
                val = marker.read_text().strip()
                if val:
                    return val
        except OSError:
            continue
    return None


def _derive_rework(conn: sqlite3.Connection, task_id: str) -> bool:
    """True when the task's OWN status history shows rework — a backward move
    (reopened after testing/complete/review). This is the only TASK-SCOPED
    rework signal that exists: `backtrack_events` carry no task_id and a single
    session closes many tasks (one session in the live corpus closed 161), so
    attributing a session's backtrack to the closing task would SMEAR every task
    in that session to 'rework'. Richer rework — in-task re-edits, chat
    corrections — needs write-time task→observation linkage (observations.task_id,
    added separately); no completion-time heuristic can recover it. Used only to
    refine an optimistic 'success'; an explicitly-asserted non-success is never
    touched. See docs/engineering/learning-extraction.md."""
    try:
        return bool(
            conn.execute(
                "SELECT 1 FROM task_status_history "
                "WHERE task_id = ? AND old_status IN ('testing','complete','done','review') "
                "  AND new_status IN ('in_progress','open','ready','icebox') LIMIT 1",
                (task_id,),
            ).fetchone()
        )
    except sqlite3.Error as exc:
        logger.debug("rework derivation skipped for %s: %s", task_id, exc)
        return False


def record_outcome(
    *,
    task_id: str,
    task_type: str,
    outcome: str,
    msg: str = "",
    skills_used: str | None = None,
    model: str | None = None,
    duration_min: int | None = None,
    refine_from_history: bool = True,
    db_path: str | Path | None = None,
) -> dict:
    """Write a task outcome to the task_outcomes table.

    Args:
        task_id: Task identifier (e.g. "TASK-140").
        task_type: Task type (e.g. "feat", "fix").
        outcome: One of: success, rework, partial, blocked.
        msg: Task summary message.
        db_path: Path to DB. Defaults to DEFAULT_DB_PATH.

    Returns:
        Dict with status.
    """
    path = Path(db_path or DEFAULT_DB_PATH)

    if not path.exists():
        logger.info("No DB at %s, skipping outcome recording", path)
        return {"status": "skipped", "reason": "db_absent"}

    if outcome not in VALID_OUTCOMES:
        return {"status": "error", "reason": f"Invalid outcome: {outcome}"}

    complexity, dimensions = _read_gate_file()
    domain = _detect_domain(task_id, msg)

    # Auto-resolve the high-value learning columns when the caller did not
    # supply them, so every completion path (CLI task-done AND MCP
    # cos_task_move) feeds skills/model/duration — without these,
    # skill_correlation mining and routing_weights are permanently starved.
    if skills_used is None:
        skills_used = _read_active_skills()
    if model is None:
        model = _resolve_model()

    conn = get_connection(path)
    try:
        if duration_min is None:
            try:
                drow = conn.execute(
                    "SELECT CAST((julianday('now') - julianday(started_at)) * 1440 AS INTEGER) "
                    "FROM tasks WHERE task_id = ? AND started_at IS NOT NULL",
                    (task_id,),
                ).fetchone()
                if drow and drow[0] is not None and drow[0] >= 0:
                    duration_min = int(drow[0])
            except sqlite3.Error as exc:
                logger.debug("duration compute skipped for %s: %s", task_id, exc)

        # Refine an optimistic 'success' into the honest 'rework' when the
        # task's own history shows it — the only thing that gives the variance
        # gate + rework extractors a non-monotone signal to learn from.
        if refine_from_history and outcome == "success" and _derive_rework(conn, task_id):
            outcome = "rework"

        # Read current outcome BEFORE update (for breakthrough detection)
        previous_outcome = None
        existing = conn.execute(
            "SELECT task_id, outcome FROM task_outcomes WHERE task_id = ?", (task_id,)
        ).fetchone()

        if existing:
            previous_outcome = existing["outcome"]
            conn.execute(
                "UPDATE task_outcomes SET outcome = ?, type = ?, domain = ?, "
                "complexity = ?, dimensions = ?, "
                "skills_used = COALESCE(?, skills_used), "
                "model = COALESCE(?, model), "
                "duration_min = COALESCE(?, duration_min) "
                "WHERE task_id = ?",
                (
                    outcome,
                    task_type,
                    domain,
                    complexity,
                    dimensions,
                    skills_used,
                    model,
                    duration_min,
                    task_id,
                ),
            )
        else:
            conn.execute(
                "INSERT INTO task_outcomes "
                "(task_id, type, domain, complexity, dimensions, outcome, "
                "skills_used, model, duration_min) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    task_id,
                    task_type,
                    domain,
                    complexity,
                    dimensions,
                    outcome,
                    skills_used,
                    model,
                    duration_min,
                ),
            )

        # Append to outcome_history (append-only transition log)
        is_breakthrough = (
            1
            if previous_outcome in ("rework", "partial", "blocked") and outcome == "success"
            else 0
        )
        try:
            conn.execute(
                "INSERT INTO outcome_history "
                "(task_id, outcome, previous_outcome, is_breakthrough, triggered_by) "
                "VALUES (?, ?, ?, ?, ?)",
                (task_id, outcome, previous_outcome, is_breakthrough, "record_outcome"),
            )
        except Exception:
            pass  # outcome_history may not exist yet (pre-v4 DB)

        conn.commit()

        result = {"status": "recorded", "task_id": task_id, "outcome": outcome}
        if is_breakthrough:
            result["is_breakthrough"] = True
            result["previous_outcome"] = previous_outcome
            logger.info(
                "BREAKTHROUGH detected for %s: %s → %s",
                task_id,
                previous_outcome,
                outcome,
            )
        else:
            logger.info(
                "Recorded outcome for %s: %s (%s, %s)", task_id, outcome, domain, complexity
            )

        return result
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Record task outcome to coding-os.db")
    parser.add_argument("--task", required=True, help="Task ID (e.g. TASK-140)")
    parser.add_argument("--type", required=True, dest="task_type", help="Task type (feat/fix/...)")
    parser.add_argument("--outcome", required=True, help="success/rework/partial/blocked")
    parser.add_argument("--msg", default="", help="Task summary")
    args = parser.parse_args()

    result = record_outcome(
        task_id=args.task,
        task_type=args.task_type,
        outcome=args.outcome,
        msg=args.msg,
    )

    if result["status"] == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
