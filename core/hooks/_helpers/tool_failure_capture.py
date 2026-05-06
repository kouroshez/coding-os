"""PostToolUseFailure hook helper — capture meaningful tool failures to DB."""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


_BLOCKED_MARKER = "BLOCKED"  # cos hook block messages start with this
_SKIP_TOOLS = frozenset({"Bash"})  # Bash failures are too noisy — skip by default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _is_hook_blocked(error: str) -> bool:
    return _BLOCKED_MARKER in error


def _extract_file_path(tool_input: dict) -> str:
    """Best-effort extraction of file path from tool_input."""
    for key in ("file_path", "path", "command"):
        if val := tool_input.get(key, ""):
            if isinstance(val, str):
                return val[:200]
    return ""


def _dedup_check(conn: sqlite3.Connection, session_id: str, content_hash: str) -> bool:
    """Return True if same (session, content_hash) already recorded within 60s."""
    row = conn.execute(
        "SELECT 1 FROM observations "
        "WHERE session_id=? AND content_hash=? "
        "  AND created_at >= datetime('now', '-60 seconds') LIMIT 1",
        (session_id, content_hash),
    ).fetchone()
    return row is not None


def capture(conn: sqlite3.Connection, session_id: str, payload: dict) -> str:
    """Write observation for this failure event. Returns status."""
    if not _table_exists(conn, "observations"):
        return "no_table"

    tool_name = payload.get("tool_name", "")
    error = payload.get("error", "")
    tool_input = payload.get("tool_input", {}) or {}

    if not tool_name or not error:
        return "empty_payload"
    if tool_name in _SKIP_TOOLS and not _is_hook_blocked(error):
        return "skipped_noisy"

    file_path = _extract_file_path(tool_input)
    blocked = _is_hook_blocked(error)
    memory_type = "hook_block" if blocked else "error"

    title = f"{'[BLOCKED] ' if blocked else ''}Tool failure: {tool_name}"
    if file_path:
        title += f" on {Path(file_path).name}"
    narrative = error[:500]

    import hashlib
    content_hash = hashlib.sha256(
        f"{session_id}:{tool_name}:{error[:100]}".encode()
    ).hexdigest()[:16]

    if _dedup_check(conn, session_id, content_hash):
        return "deduped"

    conn.execute(
        "INSERT INTO observations "
        "(session_id, tool_name, observation_type, memory_type, impact_score, "
        " title, narrative, facts, concepts, files_modified, content_hash, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            tool_name,
            "tool_failure",
            memory_type,
            0.6 if blocked else 0.3,
            title,
            narrative,
            json.dumps({"blocked": blocked, "error_snippet": error[:100]}),
            json.dumps(["tool_failure", tool_name, "hook_block" if blocked else "error"]),
            file_path or None,
            content_hash,
            _now_iso(),
        ),
    )
    conn.commit()
    return "captured"


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        return 0
    session_id, db_path = argv[1], argv[2]
    if not session_id or not db_path:
        return 0

    try:
        raw = sys.stdin.read(4096)
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        return 0  # no stdin or bad JSON — not an error

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        capture(conn, session_id, payload)
        conn.close()
    except Exception:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
