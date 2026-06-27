#!/usr/bin/env bash
# warn-abandoned-task.sh — Stop hook.
#
# Warns once per session when a task this session moved to in_progress
# or testing is still open at turn-end. Catches the recurring "agent
# started a task but never moved it to complete" pattern that strands
# cards on the board. Fail-open: never blocks the Stop, only nudges via
# a Stop additionalContext block. Debounced per session-id.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook warn-abandoned-task enter || true

[ -f "${COS_DB_PATH:-}" ] || exit 0
# Upgrade panel id from the Stop payload so $COS_SESSION_FILE
# resolves THIS panel; fall back to stdin session_id then legacy agent-dir.
INPUT="$(cos_read_stdin_bounded 2 2>/dev/null || true)"
command -v cos_panel_upgrade_from_payload >/dev/null 2>&1 && cos_panel_upgrade_from_payload "$INPUT" 2>/dev/null || true
SESSION_ID="$(cat "${COS_SESSION_FILE:-}" 2>/dev/null || true)"
if [ -z "$SESSION_ID" ] && [ -n "$INPUT" ] && command -v jq >/dev/null 2>&1; then
  SESSION_ID=$(printf '%s' "$INPUT" | jq -r '.session_id // .sessionId // empty' 2>/dev/null || true)
fi
if [ -z "$SESSION_ID" ] && [ -f "${COS_AGENT_DIR}/session-id" ]; then
  SESSION_ID=$(cat "${COS_AGENT_DIR}/session-id" 2>/dev/null || true)
fi
[ -n "$SESSION_ID" ] || exit 0
# Session-id is alnum + dash only; reject anything else before it reaches SQL.
case "$SESSION_ID" in
  *[!A-Za-z0-9-]*) exit 0 ;;
esac

# Compute the open set FIRST so the debounce can re-arm when it changes.
# `testing` is included: the testing-first protocol parks near-done work there,
# so it is the status a task most often dies in.
STUCK="$(sqlite3 "$COS_DB_PATH" \
  "SELECT group_concat(task_id || ' (' || status || ')', ', ') FROM tasks
   WHERE status IN ('in_progress','testing') AND agent_session = '$SESSION_ID';" \
  2>/dev/null || true)"
[ -n "$STUCK" ] || exit 0

# Debounce keyed on (session-id, open-set), not session-id alone — so the nudge
# re-arms on a state-change (in_progress→testing, or a close+open) instead of
# going silent for the whole session after the first warning (the "85%-done
# then stopped" gap). An unchanged open-set stays debounced (no alarm fatigue).
MARKER="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.abandoned-task-warned"  # panel-first: matches session-context panel-scope clear
STUCK_SIG=$(printf '%s' "$STUCK" | cksum | cut -d' ' -f1)
DEBOUNCE_KEY="${SESSION_ID}:${STUCK_SIG}"
if [ -f "$MARKER" ] && grep -qF "$DEBOUNCE_KEY" "$MARKER" 2>/dev/null; then
  exit 0
fi

echo "$DEBOUNCE_KEY" >> "$MARKER"
cos_log_hook warn-abandoned-task warn || true
MSG="[board] Task(s) still open for this session: ${STUCK}. Close each with \`cos task-done\` (or park via \`cos task-move --to blocked\`) — a task left in in_progress/testing is stranded on the board with no owner action."
printf '{"hookSpecificOutput":{"hookEventName":"Stop","additionalContext":%s}}\n' \
  "$(printf '%s' "$MSG" | jq -R -s '.')"

cos_log_hook warn-abandoned-task ok || true
exit 0
