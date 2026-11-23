#!/usr/bin/env bash
# sync-task-current.sh (PostToolUse) — fan-out: auto-write the per-panel
# .task-current marker when a task transitions to in_progress, so the agent
# never hand-runs `write-state.sh .task-current` after cos task-start /
# cos_task_move (the screenshot-3 anti-pattern).
#
# Panel-env reliable: a PostToolUse hook runs in the session process
# lineage, so write-state.sh resolves the correct $COS_PANEL_DIR (the MCP
# server and a `cos` CLI subprocess do NOT — they resolve a stale/other
# panel). That is why this fan-out is a hook, not an MCP/CLI side effect.
#
# Fail-open: always exit 0; a failed marker write never affects the move.
set -euo pipefail
source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"

# Fast-path: this fan-out only acts on task transitions — the cos_task_move
# tool or a Bash `cos task-start|task-move|task-done`. Every trigger contains
# the literal "task". If the raw payload has no "task" there is nothing to sync;
# bail before the panel-upgrade + jq spawns (fires on EVERY Bash tool call).
case "$INPUT" in
  *task*) ;;
  *) exit 0 ;;
esac

# Upgrade panel id from stdin session_id so the write-state.sh
# subprocess below resolves THIS panel's dir, not a stale ppid-derived one.
command -v cos_panel_upgrade_from_payload >/dev/null 2>&1 && cos_panel_upgrade_from_payload "$INPUT" 2>/dev/null || true
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")

# A task leaving active work (complete/archive/blocked/icebox — the real status
# names) must FREE the marker — otherwise it fossilises and a later commit /
# banner is wrongly attributed to it. testing keeps the marker (the banner still
# names it), but enforce-task-start only lets edits through while it is
# in_progress or emergency.
_SET_STATES='in_progress|emergency'
_CLEAR_STATES='complete|archive|blocked|icebox'

TASK_ID=""        # set the marker to this
CLEAR_FOR=""      # clear the marker IF it points at this
case "$TOOL" in
  *cos_task_move*)
    TO=$(echo "$INPUT" | jq -r '.tool_input.to // empty' 2>/dev/null || echo "")
    TID=$(echo "$INPUT" | jq -r '.tool_input.task_id // empty' 2>/dev/null || echo "")
    if [[ "$TO" =~ ^(${_SET_STATES})$ ]]; then
      TASK_ID="$TID"
    elif [[ "$TO" =~ ^(${_CLEAR_STATES})$ ]]; then
      CLEAR_FOR="$TID"
    else
      exit 0
    fi
    ;;
  Bash)
    # `cos` must sit in command position: a test or echo that merely contains
    # a task-move command must not rebind the panel.
    CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")
    if printf '%s' "$CMD" | grep -qE '(^|[;&|])[[:space:]]*cos +task-start +TASK-([A-Z][A-Z0-9]*-)?[0-9]+' 2>/dev/null; then
      TASK_ID=$(printf '%s' "$CMD" | grep -oE 'TASK-([A-Z][A-Z0-9]*-)?[0-9]+' | head -1 || echo "")
    elif printf '%s' "$CMD" | grep -qE "(^|[;&|])[[:space:]]*cos +task-move +TASK-([A-Z][A-Z0-9]*-)?[0-9]+.*--to[ =]+(${_SET_STATES})" 2>/dev/null; then
      TASK_ID=$(printf '%s' "$CMD" | grep -oE 'TASK-([A-Z][A-Z0-9]*-)?[0-9]+' | head -1 || echo "")
    elif printf '%s' "$CMD" | grep -qE '(^|[;&|])[[:space:]]*cos +task-done +TASK-([A-Z][A-Z0-9]*-)?[0-9]+' 2>/dev/null; then
      CLEAR_FOR=$(printf '%s' "$CMD" | grep -oE 'TASK-([A-Z][A-Z0-9]*-)?[0-9]+' | head -1 || echo "")
    elif printf '%s' "$CMD" | grep -qE "(^|[;&|])[[:space:]]*cos +task-move +TASK-([A-Z][A-Z0-9]*-)?[0-9]+.*--to[ =]+(${_CLEAR_STATES})" 2>/dev/null; then
      CLEAR_FOR=$(printf '%s' "$CMD" | grep -oE 'TASK-([A-Z][A-Z0-9]*-)?[0-9]+' | head -1 || echo "")
    fi
    ;;
  *) exit 0 ;;
esac

if [[ -n "$CLEAR_FOR" ]]; then
  # Only clear when THIS panel's marker actually points at the finished task —
  # never wipe a sibling task the panel may have switched to.
  marker="${COS_PANEL_DIR:-${COS_AGENT_DIR:-.coding-os/claude}}/.task-current"
  # Whole-id match: a short id must not clear a marker naming a longer one.
  if [[ -f "$marker" ]] && grep -qE "(^|[^A-Za-z0-9-])${CLEAR_FOR}([^0-9]|\$)" "$marker" 2>/dev/null; then
    # Remove the marker at the exact path we read — write-state.sh rejects an
    # empty value (`${2:?}`), so clearing means deleting the per-panel file.
    # An absent .task-current reads as task=none; a later task-start recreates it.
    rm -f "$marker" 2>/dev/null || true
    cos_log_hook sync-task-current "cleared task=${CLEAR_FOR}" 2>/dev/null || true
  fi
  exit 0
fi

[[ -z "$TASK_ID" ]] && exit 0
# Bind only a task the board really moved: a rejected move, or a command that
# merely mentions one, leaves its file outside in_progress / emergency.
source "$(dirname "$0")/check-state.sh" 2>/dev/null || true
if type cos_task_status >/dev/null 2>&1; then
  _STATUS=$(cos_task_status "$TASK_ID" 2>/dev/null || true)
  if [[ ! "$_STATUS" =~ ^(${_SET_STATES})$ ]]; then
    cos_log_hook sync-task-current "skip task=${TASK_ID} status=${_STATUS:-none}" 2>/dev/null || true
    exit 0
  fi
fi
bash "$(dirname "$0")/write-state.sh" .task-current "$TASK_ID" 2>/dev/null || true
cos_log_hook sync-task-current "set task=${TASK_ID}" 2>/dev/null || true
exit 0
