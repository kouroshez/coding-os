#!/usr/bin/env bash
# PostToolUse hook: fire-and-forget observation recording (TASK-151).
#
# Spawns capture.py in background for Write/Edit tools only. Must return
# in <1ms — all work happens in a background process. If capture.py
# itself fails (DB path broken, schema stale, import error), its stderr
# is redirected to $COS_STATE_DIR/.capture-errors.log so the Stop hook
# (check-capture-worked.sh) can surface the silent failure at session
# end instead of us losing observations invisibly for an entire session.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
INPUT="$(cos_read_stdin_bounded 2)"
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null || echo "")

COS_STATE_DIR="${COS_STATE_DIR:-.coding-os}"

# Heartbeat: prove the hook fires at all. If `cos hooks-log` shows no
# entries from this hook, Claude Code is not delivering the PostToolUse
# Write|Edit event (typically because .claude/settings.json changed
# mid-session — reload to pick up new hook config).
cos_log_hook capture-observation fire "tool=${TOOL_NAME}"

# Only capture Write and Edit tool calls (skip Read, Glob, Grep, Bash)
case "$TOOL_NAME" in
  Write|Edit) ;;
  *) exit 0 ;;
esac

CAPTURE_PY="$(dirname "$0")/../thinking_os/capture.py"
if [ ! -f "$CAPTURE_PY" ]; then
  exit 0
fi

# Ensure state dir exists for the error log (best-effort).
mkdir -p "$COS_STATE_DIR" 2>/dev/null || true
ERROR_LOG="$COS_STATE_DIR/.capture-errors.log"

# Fire-and-forget with stderr capture. The `2>>` appends any python
# traceback or exception from the background process so we can later
# detect a silent death without losing the <1ms hook budget.
(
  echo "$INPUT" | python3 "$CAPTURE_PY" 2>>"$ERROR_LOG"
) > /dev/null 2>&1 &

exit 0
