#!/usr/bin/env python3
"""
Thinking OS — Record experiment to experiment_log table (TASK-140).

Called via `make record-experiment` or directly.
Writes to coding-os.db if it exists, exits silently otherwise.

Usage:
    python record_experiment.py --task TASK-140 --hypothesis "..." --outcome "pass" --learning "..."
    python record_experiment.py --task TASK-140 --hypothesis "..." --test "..." --outcome "fail" --learning "..."
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from database import DEFAULT_DB_PATH, get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("thinking_os.experiment")


def record_experiment(
    *,
    task_id: str,
    hypothesis: str,
    test_description: str | None = None,
    outcome: str | None = None,
    learning: str | None = None,
    db_path: str | Path | None = None,
) -> dict:
    """Write an experiment record to the experiment_log table.

    Args:
        task_id: Task identifier (e.g. "TASK-140").
        hypothesis: What was being tested.
        test_description: How it was tested (optional).
        outcome: Result — pass/fail/partial (optional).
        learning: What was learned (optional).
        db_path: Path to DB. Defaults to DEFAULT_DB_PATH.

    Returns:
        Dict with id and status, or skip message.
    """
    path = Path(db_path or DEFAULT_DB_PATH)

    if not path.exists():
        logger.info("No DB found at %s, skipping experiment recording", path)
        return {"status": "skipped", "reason": "db_absent"}

    if not hypothesis.strip():
        return {"status": "error", "reason": "hypothesis is required"}

    conn = get_connection(path)
    try:
        cursor = conn.execute(
            "INSERT INTO experiment_log (task_id, hypothesis, test_description, outcome, learning) "
            "VALUES (?, ?, ?, ?, ?)",
            (task_id, hypothesis, test_description, outcome, learning),
        )
        conn.commit()
        logger.info("Recorded experiment for %s (id=%d)", task_id, cursor.lastrowid)
        return {"status": "recorded", "id": cursor.lastrowid, "task_id": task_id}
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Record an experiment to coding-os.db")
    parser.add_argument("--task", required=True, help="Task ID (e.g. TASK-140)")
    parser.add_argument("--hypothesis", required=True, help="What is being tested")
    parser.add_argument("--test", default=None, help="How it was tested")
    parser.add_argument("--outcome", default=None, help="Result: pass/fail/partial")
    parser.add_argument("--learning", default=None, help="What was learned")
    args = parser.parse_args()

    result = record_experiment(
        task_id=args.task,
        hypothesis=args.hypothesis,
        test_description=args.test,
        outcome=args.outcome,
        learning=args.learning,
    )

    if result["status"] == "recorded":
        print(f"Experiment recorded (id={result['id']}) for {result['task_id']}")
    elif result["status"] == "skipped":
        print("DB not found, experiment not recorded (this is OK)")
    else:
        print(f"Error: {result.get('reason', 'unknown')}")
        sys.exit(1)


if __name__ == "__main__":
    main()
