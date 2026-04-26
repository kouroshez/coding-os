#!/usr/bin/env bash
# Stop hook: Record enriched session summary to thinking_os.db.
# Agent-agnostic: uses COS_STATE_DIR and COS_DB_PATH.
# Fire-and-forget — never blocks or errors visibly.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

SESSION_ID=""
if [ -f "$COS_SESSION_FILE" ]; then
  SESSION_ID=$(cat "$COS_SESSION_FILE")
fi
# No extra `session=` in the detail — cos_log_hook already emits the
# identity triplet (agent=X session=Y task=Z) in the standard prefix.
cos_log_hook session-end fire

if [ ! -f "$COS_DB_PATH" ]; then
  exit 0
fi

ACTIVE_TASK=""
if [ -f "docs/tasks.md" ]; then
  ACTIVE_TASK=$(grep '^\- \[/\]' docs/tasks.md | head -1 | grep -oE 'TASK-[0-9]+' || true)
fi

run_bounded_python() {
  local script="$1"
  local timeout_s="${2:-2}"
  python3 -c '
import subprocess
import sys

script, timeout_s, *args = sys.argv[1:]
try:
    subprocess.run(
        [sys.executable, script, *args],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=float(timeout_s),
        check=False,
    )
except Exception:
    pass
' "$script" "$timeout_s" "$SESSION_ID" "$ACTIVE_TASK" "$COS_DB_PATH" >/dev/null 2>&1 || true
}

# Find scripts in coding-os core or legacy .claude path
for SCRIPT_DIR in "$(dirname "$0")/../thinking_os" ".claude/thinking_os" "$(dirname "$0")/../thinking_os" ".claude/thinking_os"; do
  if [ -f "${SCRIPT_DIR}/session_summary.py" ]; then
    run_bounded_python "${SCRIPT_DIR}/session_summary.py" 2
    break
  fi
done

for SCRIPT_DIR in "$(dirname "$0")/../thinking_os" ".claude/thinking_os" "$(dirname "$0")/../thinking_os" ".claude/thinking_os"; do
  if [ -f "${SCRIPT_DIR}/session_enrich.py" ]; then
    run_bounded_python "${SCRIPT_DIR}/session_enrich.py" 2
    break
  fi
done
