#!/usr/bin/env python3
"""
Thinking OS — Enriched session summary builder.

Called by session-end.sh Stop hook. Aggregates observation counts,
files touched, and breakthrough IDs from the current session.
Links to previous session for episode chaining.

Always exits 0 — never blocks the caller.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from db import DEFAULT_DB_PATH, get_connection

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("thinking_os.session_summary")


def build_session_summary(
    *,
    session_id: str,
    task_id: str | None = None,
    db_path: str | Path | None = None,
) -> dict:
    """Build enriched session summary from observations and outcomes.

    Args:
        session_id: Current session identifier.
        task_id: Active task (if any).
        db_path: Path to DB. Defaults to DEFAULT_DB_PATH.

    Returns:
        Dict with status and summary data.
    """
    path = Path(db_path or DEFAULT_DB_PATH)

    if not path.exists():
        return {"status": "skipped", "reason": "db_absent"}

    if not session_id:
        return {"status": "skipped", "reason": "no_session_id"}

    conn = get_connection(path)
    try:
        # 1. Count observations for this session
        obs_count = conn.execute(
            "SELECT COUNT(*) FROM observations WHERE session_id = ?",
            (session_id,),
        ).fetchone()[0]

        # 2. Aggregate distinct files modified
        file_rows = conn.execute(
            "SELECT DISTINCT files_modified FROM observations "
            "WHERE session_id = ? AND files_modified IS NOT NULL",
            (session_id,),
        ).fetchall()
        files_touched = ",".join(r[0] for r in file_rows if r[0])

        # 3. Find breakthrough IDs from outcome_history (pre-v4 DBs won't have this table)
        breakthrough_ids = ""
        try:
            bt_rows = conn.execute(
                "SELECT task_id FROM outcome_history "
                "WHERE is_breakthrough = 1 AND created_at >= datetime('now', '-4 hours') "
                "ORDER BY created_at DESC LIMIT 5",
            ).fetchall()
            breakthrough_ids = ",".join(r[0] for r in bt_rows if r[0])
        except sqlite3.OperationalError as exc:
            logger.warning(
                "outcome_history query failed (pre-v4 DB?): %s — "
                "breakthrough ids will be empty for this session",
                exc,
            )

        # 4. Find previous session ID for episode chaining
        prev_row = conn.execute(
            "SELECT session_id FROM session_summaries "
            "WHERE session_id != ? "
            "ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        previous_session_id = prev_row[0] if prev_row else None

        # 5. UPSERT into session_summaries
        existing = conn.execute(
            "SELECT id FROM session_summaries WHERE session_id = ?",
            (session_id,),
        ).fetchone()

        if existing:
            conn.execute(
                "UPDATE session_summaries SET "
                "task_id = COALESCE(?, task_id), "
                "previous_session_id = ?, "
                "files_touched = ?, "
                "observations_count = ?, "
                "breakthrough_ids = ? "
                "WHERE id = ?",
                (task_id, previous_session_id, files_touched,
                 obs_count, breakthrough_ids, existing[0]),
            )
        else:
            conn.execute(
                "INSERT INTO session_summaries "
                "(session_id, task_id, previous_session_id, files_touched, "
                "observations_count, breakthrough_ids) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, task_id, previous_session_id, files_touched,
                 obs_count, breakthrough_ids),
            )

        conn.commit()
        logger.info(
            "Session summary for %s: %d observations, %d files, breakthroughs: %s",
            session_id, obs_count, len(file_rows), breakthrough_ids or "none",
        )
        return {
            "status": "recorded",
            "session_id": session_id,
            "observations_count": obs_count,
            "files_touched": files_touched,
            "breakthrough_ids": breakthrough_ids,
            "previous_session_id": previous_session_id,
        }
    finally:
        conn.close()


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(0)

    session_id = sys.argv[1]
    task_id = sys.argv[2] if len(sys.argv) > 2 else None
    db_path = sys.argv[3] if len(sys.argv) > 3 else None

    build_session_summary(
        session_id=session_id,
        task_id=task_id,
        db_path=db_path,
    )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        sys.exit(0)
