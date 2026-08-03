#!/usr/bin/env bash
# warn-abandoned-task.sh — Stop hook.
#
# Warns at turn-end about two abandonment shapes owned by THIS session:
#   1. a task moved to in_progress/testing and left open (the classic
#      "started but never completed" strand), and
#   2. a card the session CREATED and left un-ready in icebox — a silent
#      create-then-park, invisible to cos_task_pick/claim_next (attributed
#      via the task_status_history 'created' row; ready/parked/keep exempt).
# Fail-open: never blocks the Stop, only nudges via a Stop additionalContext
# block. Debounced per (session-id, open-set) so it re-arms on state change.
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
# so it is the status a task most often dies in. A task bound in a LIVE
# sibling panel is skipped — two panels can share one session id (resumed
# conversation), and warning the idle one about its sibling's live work
# invited "rescue" parks (the phantom NULL-reason reverts).
STUCK=""
while IFS='|' read -r _t _s; do
  [ -n "$_t" ] || continue
  if command -v cos_task_bound_in_live_sibling >/dev/null 2>&1 \
     && cos_task_bound_in_live_sibling "$_t"; then
    continue
  fi
  STUCK="${STUCK:+$STUCK, }$_t ($_s)"
done < <(sqlite3 "$COS_DB_PATH" \
  "SELECT task_id || '|' || status FROM tasks
   WHERE status IN ('in_progress','testing') AND agent_session = '$SESSION_ID';" \
  2>/dev/null || true)

# Create-then-park: icebox cards THIS session CREATED and left un-ready. The
# creating session comes from the task_status_history 'created' row (old_status=''
# sentinel written by cos_task_create), so a parked card whose tasks.agent_session
# is NULL is still attributed to its author — the exact blind spot warn-abandoned
# had on the parked lane. A 'ready' card is a deliberate pull-queue and a
# 'parked'/'keep' card is deliberate backlog: both exempt (COALESCE so a card with
# no labels_json still matches). Only silent create-then-drift is surfaced.
PARKED="$(sqlite3 "$COS_DB_PATH" \
  "SELECT group_concat(t.task_id, ', ') FROM tasks t
   JOIN task_status_history h
     ON h.task_id = t.task_id AND h.old_status = '' AND h.reason = 'created'
   WHERE t.status = 'icebox' AND h.agent_session = '$SESSION_ID'
     AND COALESCE(t.labels_json,'') NOT LIKE '%\"ready\"%'
     AND COALESCE(t.labels_json,'') NOT LIKE '%\"parked\"%'
     AND COALESCE(t.labels_json,'') NOT LIKE '%\"keep\"%';" \
  2>/dev/null || true)"
[ -n "$STUCK$PARKED" ] || exit 0

# Debounce keyed on (session-id, both open-sets), not session-id alone — so the
# nudge re-arms on any state-change (in_progress→testing, a close+open, a new
# parked card) instead of going silent for the whole session after the first
# warning (the "85%-done then stopped" gap). An unchanged set stays debounced.
MARKER="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.abandoned-task-warned"  # panel-first: matches session-context panel-scope clear
STUCK_SIG=$(printf '%s' "$STUCK|$PARKED" | cksum | cut -d' ' -f1)
DEBOUNCE_KEY="${SESSION_ID}:${STUCK_SIG}"
if [ -f "$MARKER" ] && grep -qF "$DEBOUNCE_KEY" "$MARKER" 2>/dev/null; then
  exit 0
fi

echo "$DEBOUNCE_KEY" >> "$MARKER"
cos_log_hook warn-abandoned-task warn || true
MSG=""
if [ -n "$STUCK" ]; then
  MSG="[board] Task(s) still open for this session: ${STUCK}. Close each with \`cos task-done\` (or park via \`cos task-move --to blocked --reason '<why>'\`) — a task left in in_progress/testing is stranded on the board with no owner action. Never park work you did not start this conversation."
fi
if [ -n "$PARKED" ]; then
  [ -n "$MSG" ] && MSG="${MSG}"$'\n'
  MSG="${MSG}[board] Card(s) you created and left un-ready in icebox this session: ${PARKED}. An un-ready icebox card is invisible to \`cos_task_pick\`/\`cos_task_claim_next\` — nobody will pull it. Start it (\`cos task-start\`), queue it (\`cos task-ready\`), or add a \`parked\`/\`keep\` label if it is deliberate long-term backlog."
fi
printf '{"hookSpecificOutput":{"hookEventName":"Stop","additionalContext":%s}}\n' \
  "$(printf '%s' "$MSG" | jq -R -s '.')"

cos_log_hook warn-abandoned-task ok || true
exit 0
