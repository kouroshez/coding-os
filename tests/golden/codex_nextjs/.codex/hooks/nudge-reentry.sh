#!/usr/bin/env bash
# nudge-reentry.sh — UserPromptSubmit hook.
#
# Softly reminds the agent, once per (session, open-set), when a new prompt
# arrives while THIS session holds an in_progress task not bound to
# .task-current. Closes the re-entry blind spot the Stop-time
# warn-abandoned-task cannot cover — a turn that never reached Stop, or
# .task-current drifting from the DB (common on Codex, whose MCP task-moves
# fire no .task-current sync). Session-scoped (agent_session), so a sibling
# session's WIP never false-triggers — the board-global banner wip= count
# cannot make that distinction. Fail-open: emits one additionalContext line
# and exits 0, never blocks. Debounced per (session, in_progress-set).
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook nudge-reentry enter || true

[ -f "${COS_DB_PATH:-}" ] || exit 0
command -v sqlite3 >/dev/null 2>&1 || exit 0

# Upgrade panel id from the payload so $COS_SESSION_FILE / $COS_PANEL_DIR
# resolve THIS panel; fall back to stdin session_id then legacy agent-dir.
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

# in_progress tasks owned by THIS session. `testing` is excluded — it is a
# legitimate parked state (verification running) that .task-current may not
# point at, so only actively-owned in_progress work counts as "unbound".
OPEN="$(sqlite3 "$COS_DB_PATH" \
  "SELECT group_concat(task_id, ',') FROM tasks
   WHERE status = 'in_progress' AND agent_session = '$SESSION_ID';" \
  2>/dev/null || true)"
[ -n "$OPEN" ] || exit 0

# Bound task marker (panel-first, matching session-context's TASK_CUR read).
# write-state.sh prefixes a session id ("<sid> <task>"), so take the LAST
# whitespace field — a raw cat|head -c 32 only ever saw the 31-char sid and
# made this bound-check dead code in production.
TASK_CUR="$(awk '{print $NF}' "${COS_PANEL_DIR:-$COS_AGENT_DIR}/.task-current" 2>/dev/null | head -1 || true)"
[ -n "$TASK_CUR" ] || TASK_CUR="$(awk '{print $NF}' "${COS_AGENT_DIR}/.task-current" 2>/dev/null | head -1 || true)"
TASK_CUR="$(printf '%s' "$TASK_CUR" | tr -d '\n\r' | head -c 32)"

# Bound iff .task-current names one of the session's in_progress tasks. When it
# does, the agent is correctly re-entered — stay silent.
case ",$OPEN," in
  *",$TASK_CUR,"*) [ -n "$TASK_CUR" ] && exit 0 ;;
esac

# A task bound in a LIVE sibling panel is actively driven there — drop it from
# this panel's nudge set. Two panels can share one session id (resumed
# conversation mirrors the agent-level id), and nudging the idle one about its
# sibling's live work invited the "rescue" parks recorded as phantom
# NULL-reason in_progress→icebox reverts. Real strands still nudge.
if command -v cos_task_bound_in_live_sibling >/dev/null 2>&1; then
  KEEP=""
  OLDIFS=$IFS; IFS=','
  for t in $OPEN; do
    [ -n "$t" ] || continue
    if cos_task_bound_in_live_sibling "$t"; then continue; fi
    KEEP="${KEEP:+$KEEP,}$t"
  done
  IFS=$OLDIFS
  OPEN="$KEEP"
  if [ -z "$OPEN" ]; then
    cos_log_hook nudge-reentry skip "reason=sibling_bound" || true
    exit 0
  fi
fi

# Debounce keyed on (session, open-set), not session alone — so the nudge
# re-arms when the in_progress set changes but an unchanged mismatch stays
# quiet (no alarm fatigue). Panel-first marker matches session-context scope.
MARKER="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.reentry-nudged"
OPEN_SIG=$(printf '%s' "$OPEN" | cksum | cut -d' ' -f1)
DEBOUNCE_KEY="${SESSION_ID}:${OPEN_SIG}"
if [ -f "$MARKER" ] && grep -qF "$DEBOUNCE_KEY" "$MARKER" 2>/dev/null; then
  exit 0
fi
echo "$DEBOUNCE_KEY" >> "$MARKER"

cos_log_hook nudge-reentry warn || true
MSG="[board] This session holds in_progress task(s) not bound to .task-current: ${OPEN}. Re-bind with \`cos task-start ${OPEN%%,*}\` (or park via \`cos task-move --to blocked --reason '<why>'\`) so the pulse, work-log capture, and DoD gate track the right task. Never park work you did not start this conversation."
printf '{"hookSpecificOutput":{"hookEventName":"UserPromptSubmit","additionalContext":%s}}\n' \
  "$(printf '%s' "$MSG" | jq -R -s '.')"

cos_log_hook nudge-reentry ok || true
exit 0
