#!/usr/bin/env bash
# Phase L.4 — PostToolUse: Write/Edit on docs/tasks/*.md
# Re-syncs the single file into the DB cache so the board is fresh
# within one hook latency (<200ms per §8.2).
#
# Fail-soft: background subprocess; never blocks the tool response.

set -eu
source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

cos_log_hook "auto-task-sync" "entry" 2>/dev/null || true

payload="$(cat)"
file_path="$(echo "$payload" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))
except Exception:
    print("")
' 2>/dev/null || echo "")"

if [[ "$file_path" != *"docs/tasks/"*.md ]]; then
    exit 0
fi

# Background, fire-and-forget.
(
    COS_PROJECT_ROOT="${COS_PROJECT_ROOT:-$PWD}" python3 - "$file_path" <<'PY' >/dev/null 2>&1
import os
import sqlite3
import sys
from pathlib import Path

try:
    from core.board_os.sync import sync_one
except ImportError:
    sys.exit(0)

file_path = Path(sys.argv[1])
if not file_path.exists():
    sys.exit(0)

project_root = Path(os.environ.get("COS_PROJECT_ROOT", os.getcwd())).resolve()
db_path = os.environ.get(
    "COS_DB_PATH", str(project_root / ".coding-os" / "thinking_os.db"),
)
if not Path(db_path).exists():
    sys.exit(0)

conn = sqlite3.connect(db_path)
try:
    sync_one(conn, file_path, project_root=project_root)
finally:
    conn.close()
PY
) &

cos_log_hook "auto-task-sync" "spawned" 2>/dev/null || true
exit 0
