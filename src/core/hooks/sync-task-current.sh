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
# Upgrade panel id from stdin session_id so the write-state.sh
# subprocess below resolves THIS panel's dir, not a stale ppid-derived one.
command -v cos_panel_upgrade_from_payload >/dev/null 2>&1 && cos_panel_upgrade_from_payload "$INPUT" 2>/dev/null || true
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")

# A task leaving active work (complete/done/archived/blocked) must FREE the
# marker — otherwise it fossilises (the TASK-052 stale marker) and a later
# commit / banner is wrongly attributed to a finished task. testing keeps the
# marker (still the active task; tests run before done).
_CLEAR_STATES='complete|done|archived|blocked'

TASK_ID=""        # set the marker to this
CLEAR_FOR=""      # clear the marker IF it points at this
case "$TOOL" in
  *cos_task_move*)
    TO=$(echo "$INPUT" | jq -r '.tool_input.to // empty' 2>/dev/null || echo "")
    TID=$(echo "$INPUT" | jq -r '.tool_input.task_id // empty' 2>/dev/null || echo "")
    if [[ "$TO" == "in_progress" ]]; then
      TASK_ID="$TID"
    elif [[ "$TO" =~ ^(${_CLEAR_STATES})$ ]]; then
      CLEAR_FOR="$TID"
    else
      exit 0
    fi
    ;;
  Bash)
    CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")
    if printf '%s' "$CMD" | grep -qE 'cos +task-start +TASK-([A-Z][A-Z0-9]*-)?[0-9]+' 2>/dev/null; then
      TASK_ID=$(printf '%s' "$CMD" | grep -oE 'TASK-([A-Z][A-Z0-9]*-)?[0-9]+' | head -1 || echo "")
    elif printf '%s' "$CMD" | grep -qE 'cos +task-move +TASK-([A-Z][A-Z0-9]*-)?[0-9]+.*--to +in_progress' 2>/dev/null; then
      TASK_ID=$(printf '%s' "$CMD" | grep -oE 'TASK-([A-Z][A-Z0-9]*-)?[0-9]+' | head -1 || echo "")
    elif printf '%s' "$CMD" | grep -qE 'cos +task-done +TASK-([A-Z][A-Z0-9]*-)?[0-9]+' 2>/dev/null; then
      CLEAR_FOR=$(printf '%s' "$CMD" | grep -oE 'TASK-([A-Z][A-Z0-9]*-)?[0-9]+' | head -1 || echo "")
    elif printf '%s' "$CMD" | grep -qE "cos +task-move +TASK-([A-Z][A-Z0-9]*-)?[0-9]+.*--to +(${_CLEAR_STATES})" 2>/dev/null; then
      CLEAR_FOR=$(printf '%s' "$CMD" | grep -oE 'TASK-([A-Z][A-Z0-9]*-)?[0-9]+' | head -1 || echo "")
    fi
    ;;
  *) exit 0 ;;
esac

if [[ -n "$CLEAR_FOR" ]]; then
  # Only clear when THIS panel's marker actually points at the finished task —
  # never wipe a sibling task the panel may have switched to.
  marker="${COS_PANEL_DIR:-${COS_AGENT_DIR:-.coding-os/claude}}/.task-current"
  if [[ -f "$marker" ]] && grep -q "$CLEAR_FOR" "$marker" 2>/dev/null; then
    # Remove the marker at the exact path we read — write-state.sh rejects an
    # empty value (`${2:?}`), so clearing means deleting the per-panel file.
    # An absent .task-current reads as task=none; a later task-start recreates it.
    rm -f "$marker" 2>/dev/null || true
    cos_log_hook sync-task-current "cleared task=${CLEAR_FOR}" 2>/dev/null || true
  fi
  exit 0
fi

[[ -z "$TASK_ID" ]] && exit 0
bash "$(dirname "$0")/write-state.sh" .task-current "$TASK_ID" 2>/dev/null || true
cos_log_hook sync-task-current "set task=${TASK_ID}" 2>/dev/null || true
exit 0
