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

_HERE = Path(__file__).resolve().parent
# The session-end hook runs this as a file under an interpreter without the
# editable-install finder, so put src/ on sys.path for `from core.logging_os`
# and thinking_os/ for `from database` — else ModuleNotFoundError, swallowed silently.
_SRC = _HERE.parents[1]
for _bootstrap_path in (_SRC, _HERE):
    if str(_bootstrap_path) not in sys.path:
        sys.path.insert(0, str(_bootstrap_path))

from database import DEFAULT_DB_PATH, get_connection

_SESSION_ID_TIMESTAMP_RE = __import__("re").compile(
    r"ses-[A-Za-z0-9_-]+?-(?P<date>\d{8})-(?P<time>\d{6})(?:-[A-Za-z0-9]+)?$"
)


def _compute_session_duration(conn, session_id: str) -> int | None:
    """Return whole minutes elapsed from session start → now, or None."""
    import sqlite3 as _sq
    from datetime import datetime, timezone

    m = _SESSION_ID_TIMESTAMP_RE.search(session_id or "")
    start_dt: datetime | None = None
    if m:
        try:
            start_dt = datetime.strptime(
                f"{m['date']}{m['time']}",
                "%Y%m%d%H%M%S",
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            start_dt = None

    if start_dt is None:
        try:
            row = conn.execute(
                "SELECT MIN(created_at) FROM observations WHERE session_id = ?",
                (session_id,),
            ).fetchone()
        except _sq.OperationalError:
            return None
        raw = row[0] if row else None
        if not raw:
            return None
        try:
            start_dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if start_dt.tzinfo is None:
                start_dt = start_dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    delta = datetime.now(timezone.utc) - start_dt
    return max(0, int(delta.total_seconds() // 60))


from core.logging_os import setup as _logging_os_setup

_logging_os_setup(level="info")
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
        # 0. Derive duration_minutes. Session id carries the start time in
        #    its canonical format (ses-<agent>-YYYYMMDD-HHMMSS-xxxx).  Fall
        #    back to the earliest observation timestamp if the id is from a
        #    pre-canonical era.
        duration_minutes = _compute_session_duration(conn, session_id)

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

        # 3b. Factual completion digest — NOT a reflection (that stays with
        #     record_review.py). Gives session_startup a non-empty `completed`
        #     instead of a husk, only when the session actually did work.
        completed = None
        if obs_count:
            n_files = len([r[0] for r in file_rows if r[0]])
            completed = f"{obs_count} edit(s) across {n_files} file(s)"
            if breakthrough_ids:
                completed += f"; breakthroughs: {breakthrough_ids}"

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
                "breakthrough_ids = ?, "
                "completed = COALESCE(?, completed), "
                "duration_minutes = COALESCE(?, duration_minutes) "
                "WHERE id = ?",
                (
                    task_id,
                    previous_session_id,
                    files_touched,
                    obs_count,
                    breakthrough_ids,
                    completed,
                    duration_minutes,
                    existing[0],
                ),
            )
        else:
            conn.execute(
                "INSERT INTO session_summaries "
                "(session_id, task_id, previous_session_id, files_touched, "
                "observations_count, breakthrough_ids, completed, duration_minutes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    task_id,
                    previous_session_id,
                    files_touched,
                    obs_count,
                    breakthrough_ids,
                    completed,
                    duration_minutes,
                ),
            )

        conn.commit()
        logger.info(
            "Session summary for %s: %d observations, %d files, breakthroughs: %s",
            session_id,
            obs_count,
            len(file_rows),
            breakthrough_ids or "none",
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
