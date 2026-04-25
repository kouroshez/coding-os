#!/usr/bin/env bash
# Phase L.4 — PreToolUse: before transition to in_progress/emergency
# Checks current WIP count against cap from scrumban-config.yaml.
# Blocks if cap exceeded; env COS_WIP_OVERRIDE=1 bypasses.

set -euo pipefail
source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

cos_log_hook "enforce-wip-limit" "entry" 2>/dev/null || true

# WIP check runs through the same workflow.transition() path that MCP
# calls — bash-level hook is a belt-and-suspenders layer for the case
# where a task file is edited directly (bypassing cos_task_move).
# If board_os + config are unavailable, fail-soft.

payload="$(cat)"
file_path="$(echo "$payload" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
    print(d.get("tool_input", {}).get("file_path", ""))
except Exception:
    print("")
' 2>/dev/null || echo "")"

if [[ "$file_path" != *"docs/tasks/"*.md ]]; then
    exit 0
fi

python3 - "$payload" <<'PY'
import json
import os
import sys
from pathlib import Path

try:
    from core.board_os.parser import extract_frontmatter, is_lean_format
    from core.board_os.config import load_config
    from core.board_os.workflow import check_wip
except ImportError:
    sys.exit(0)

try:
    data = json.loads(sys.argv[1])
except Exception:
    sys.exit(0)

tool_input = data.get("tool_input", {})
content = tool_input.get("content") or ""
if "new_string" in tool_input and "old_string" in tool_input:
    p = Path(tool_input.get("file_path", ""))
    if p.exists():
        try:
            content = p.read_text(encoding="utf-8").replace(
                tool_input["old_string"], tool_input["new_string"],
            )
        except Exception:
            pass

if not content or not is_lean_format(content):
    sys.exit(0)

fm = extract_frontmatter(content)
if fm is None:
    sys.exit(0)

new_status = fm.get("status")
if new_status not in {"in_progress", "emergency"}:
    sys.exit(0)

# Distinguish transition from same-status body edit. If the on-disk
# task already has the same status we're writing back, this is just
# a body update (Outcome / Acceptance / Work Log) — not a new WIP slot.
# Only count cap usage when the status actually changes.
target_path = Path(tool_input.get("file_path", ""))
if target_path.exists():
    try:
        existing = target_path.read_text(encoding="utf-8")
        existing_fm = extract_frontmatter(existing)
        if existing_fm and existing_fm.get("status") == new_status:
            sys.exit(0)
    except Exception:
        pass

if os.environ.get("COS_WIP_OVERRIDE") == "1":
    sys.exit(0)

project_root = Path(os.environ.get("COS_PROJECT_ROOT", os.getcwd())).resolve()
try:
    config = load_config(project_root)
except (FileNotFoundError, Exception):
    sys.exit(0)

import sqlite3
db_path = os.environ.get(
    "COS_DB_PATH", str(project_root / ".coding-os" / "thinking-os.db"),
)
if not Path(db_path).exists():
    sys.exit(0)

conn = sqlite3.connect(db_path)
state = check_wip(conn, config)
conn.close()

cap = state.caps.get(new_status)
current = state.counts.get(new_status, 0)
if cap is not None and current >= cap:
    print(
        f"ERROR enforce-wip-limit: WIP cap reached for {new_status}: "
        f"{current}/{cap}. Complete another task first or set "
        f"COS_WIP_OVERRIDE=1 to force.",
        file=sys.stderr,
    )
    sys.exit(2)

sys.exit(0)
PY

exit_code=$?
cos_log_hook "enforce-wip-limit" "$([[ $exit_code -eq 0 ]] && echo allow || echo block)" 2>/dev/null || true
exit $exit_code
