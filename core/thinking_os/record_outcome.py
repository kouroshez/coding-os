#!/usr/bin/env python3
"""
Thinking OS — Record task outcome to task_outcomes table (TASK-136).

Called by task-done.sh as fire-and-forget background process.
Writes to coding-os.db if it exists, exits silently otherwise.

Usage:
    python record_outcome.py --task TASK-140 --type feat --outcome success --msg "summary"
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import DEFAULT_DB_PATH, get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("thinking_os.outcome")

VALID_OUTCOMES = {"success", "rework", "partial", "blocked"}


def _read_gate_file() -> tuple[str, int]:
    """Read complexity classification from .thinking_os-gate file.

    Format: "<session-id> <CLASSIFICATION> <N>" (session-scoped).
    Skips the session-id prefix when parsing.
    """
    gate_path = Path(os.environ.get("COS_STATE_DIR", ".coding-os") + "/.thinking_os-gate")
    if not gate_path.exists():
        return "UNKNOWN", 1
    try:
        content = gate_path.read_text().strip()
        parts = content.split()
        # Session-scoped format: "ses-xxx COMPLICATED 4"
        # Legacy format: "COMPLICATED 4"
        if parts and parts[0].startswith("ses-"):
            parts = parts[1:]  # skip session ID
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


def record_outcome(
    *,
    task_id: str,
    task_type: str,
    outcome: str,
    msg: str = "",
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

    conn = get_connection(path)
    try:
        # Read current outcome BEFORE update (for breakthrough detection)
        previous_outcome = None
        existing = conn.execute(
            "SELECT task_id, outcome FROM task_outcomes WHERE task_id = ?", (task_id,)
        ).fetchone()

        if existing:
            previous_outcome = existing["outcome"]
            conn.execute(
                "UPDATE task_outcomes SET outcome = ?, type = ?, domain = ?, "
                "complexity = ?, dimensions = ? WHERE task_id = ?",
                (outcome, task_type, domain, complexity, dimensions, task_id),
            )
        else:
            conn.execute(
                "INSERT INTO task_outcomes (task_id, type, domain, complexity, dimensions, outcome) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (task_id, task_type, domain, complexity, dimensions, outcome),
            )

        # Append to outcome_history (append-only transition log)
        is_breakthrough = (
            1 if previous_outcome in ("rework", "partial", "blocked")
            and outcome == "success"
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
                task_id, previous_outcome, outcome,
            )
        else:
            logger.info("Recorded outcome for %s: %s (%s, %s)", task_id, outcome, domain, complexity)

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
