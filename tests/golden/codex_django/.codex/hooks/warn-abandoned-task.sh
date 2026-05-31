#!/usr/bin/env bash
# warn-abandoned-task.sh (Phase observability) — Stop hook.
#
# Warns once per session when a task this session moved to in_progress
# is still in_progress at turn-end. Catches the recurring "agent started
# a task but never moved it to testing/complete" pattern that strands
# cards on the board. Fail-open: never blocks the Stop, only nudges via
# a Stop additionalContext block. Debounced per session-id.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook warn-abandoned-task enter || true

[ -f "${COS_DB_PATH:-}" ] || exit 0
[ -f "${COS_SESSION_FILE:-}" ] || exit 0
SESSION_ID="$(cat "$COS_SESSION_FILE" 2>/dev/null || true)"
[ -n "$SESSION_ID" ] || exit 0
# Session-id is alnum + dash only; reject anything else before it reaches SQL.
case "$SESSION_ID" in
  *[!A-Za-z0-9-]*) exit 0 ;;
esac

# Per-session debounce — warn at most once per session-id.
MARKER="${COS_AGENT_DIR}/.abandoned-task-warned"
if [ -f "$MARKER" ] && grep -qF "$SESSION_ID" "$MARKER" 2>/dev/null; then
  exit 0
fi

STUCK="$(sqlite3 "$COS_DB_PATH" \
  "SELECT group_concat(task_id, ', ') FROM tasks
   WHERE status = 'in_progress' AND agent_session = '$SESSION_ID';" \
  2>/dev/null || true)"

if [ -n "$STUCK" ]; then
  echo "$SESSION_ID" > "$MARKER"
  cos_log_hook warn-abandoned-task warn || true
  MSG="[board] Task(s) still in_progress for this session: ${STUCK}. Move each to testing/complete with \`cos task-move\` once done — a task left in in_progress is stranded on the board with no owner action."
  printf '{"hookSpecificOutput":{"hookEventName":"Stop","additionalContext":%s}}\n' \
    "$(printf '%s' "$MSG" | jq -R -s '.')"
fi

cos_log_hook warn-abandoned-task ok || true
exit 0
