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
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null || echo "")

COS_STATE_DIR="${COS_STATE_DIR:-.coding-os}"

# Heartbeat: prove the hook fires at all. If `cos hooks-log` shows no
# entries from this hook, Claude Code is not delivering the PostToolUse
# Write|Edit event (typically because .claude/settings.json changed
# mid-session — reload to pick up new hook config).
cos_log_hook capture-observation fire "tool=${TOOL_NAME}"

# Only capture Write, Edit, MultiEdit tool calls (skip Read, Glob, Grep, Bash).
# MultiEdit is the batched variant — Claude SDK emits it for most real agent
# edits, so excluding it produced ~0 observations (capture.py CAPTURE_TOOLS
# already includes MultiEdit; the shell filter was the stale layer).
case "$TOOL_NAME" in
  Write|Edit|MultiEdit) ;;
  *) exit 0 ;;
esac

CAPTURE_PY="$(dirname "$0")/../thinking_os/capture.py"
if [ ! -f "$CAPTURE_PY" ]; then
  exit 0
fi

# Ensure state dir exists for the error log (best-effort).
mkdir -p "$COS_STATE_DIR" 2>/dev/null || true
ERROR_LOG="$COS_STATE_DIR/.capture-errors.log"

# Run capture SYNCHRONOUSLY with embedding skipped. A backgrounded
# `(...) &` was reaped by the agent hook lifecycle before capture.py's
# INSERT+commit, so observations never persisted (TASK-048: 6 inserts in
# 17 days despite the hook firing constantly). capture.py is ~one python
# startup under COS_CAPTURE_SKIP_EMBED; the FTS5 trigger indexes the row
# on INSERT so keyword recall works without the embedding. Real failures
# append a traceback to $ERROR_LOG for check-capture-worked.sh at Stop.
echo "$INPUT" | COS_CAPTURE_SKIP_EMBED=1 python3 "$CAPTURE_PY" 2>>"$ERROR_LOG" || true

# Visible signal — Claude Code does NOT render PostToolUse `systemMessage`
# directly in chat UI; route through the per-turn activity log so
# session-context.sh aggregates + emits on the next UserPromptSubmit
# (which IS rendered, mirroring the caveman pattern). systemMessage
# stays for future agent renderers + SDK consumers.
cos_record_activity memory "+obs" 2>/dev/null || true
printf '%s' '{"systemMessage":"[memory] +obs captured"}'

exit 0
