#!/usr/bin/env python3
"""Thinking OS — Doc audit-log capture (TASK-060).

Reads tool-call JSON from stdin; for Write/Edit/MultiEdit on docs/** files,
appends an immutable doc_audit_trail row via audit_log_record. The MCP tool
cos_audit_log_record stays the manual / Codex path; this hook is the
auto-capture path — symmetry with capture.py (observations). action is
tool-derived (Write -> created, Edit/MultiEdit -> updated) because at
PostToolUse the file always exists, so on-disk existence cannot distinguish
the two. Fire-and-forget: exits silently (0) on any error.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

CAPTURE_TOOLS = {"Write", "Edit", "MultiEdit"}


def _session_id() -> str:
    base = os.environ.get("COS_PANEL_DIR") or os.environ.get("COS_AGENT_DIR") or ""
    if not base:
        return ""
    sid_file = Path(base) / "session-id"
    if not sid_file.exists():
        return ""
    try:
        return sid_file.read_text(encoding="utf-8").strip().split(" ")[0]
    except OSError:
        return ""


def main() -> int:
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return 0
    tool = data.get("tool_name", "")
    if tool not in CAPTURE_TOOLS:
        return 0
    file_path = (data.get("tool_input", {}) or {}).get("file_path", "")
    norm = file_path.replace("\\", "/")
    if not (norm.startswith("docs/") or "/docs/" in norm):
        return 0

    action = "created" if tool == "Write" else "updated"
    try:
        from database import DEFAULT_DB_PATH, get_connection
        from tools.audit import audit_log_record
    except Exception:
        return 0
    db_path = os.environ.get("COS_DB_PATH") or str(DEFAULT_DB_PATH)
    if not Path(db_path).exists():
        return 0
    try:
        conn = get_connection(db_path)
        audit_log_record(
            conn,
            doc_path=norm,
            action=action,
            session_id=_session_id() or None,
            agent=os.environ.get("COS_AGENT") or "claude",
            reason="auto-captured on Write/Edit (capture-audit hook)",
        )
        conn.commit()
        conn.close()
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
