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
# Upgrade panel id from stdin session_id (TASK-107) so the write-state.sh
# subprocess below resolves THIS panel's dir, not a stale ppid-derived one.
command -v cos_panel_upgrade_from_payload >/dev/null 2>&1 && cos_panel_upgrade_from_payload "$INPUT" 2>/dev/null || true
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")

TASK_ID=""
case "$TOOL" in
  *cos_task_move*)
    TO=$(echo "$INPUT" | jq -r '.tool_input.to // empty' 2>/dev/null || echo "")
    [[ "$TO" == "in_progress" ]] || exit 0
    TASK_ID=$(echo "$INPUT" | jq -r '.tool_input.task_id // empty' 2>/dev/null || echo "")
    ;;
  Bash)
    CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")
    if printf '%s' "$CMD" | grep -qE 'cos +task-start +TASK-[0-9]+' 2>/dev/null; then
      TASK_ID=$(printf '%s' "$CMD" | grep -oE 'TASK-[0-9]+' | head -1 || echo "")
    elif printf '%s' "$CMD" | grep -qE 'cos +task-move +TASK-[0-9]+.*--to +in_progress' 2>/dev/null; then
      TASK_ID=$(printf '%s' "$CMD" | grep -oE 'TASK-[0-9]+' | head -1 || echo "")
    fi
    ;;
  *) exit 0 ;;
esac

[[ -z "$TASK_ID" ]] && exit 0
bash "$(dirname "$0")/write-state.sh" .task-current "$TASK_ID" 2>/dev/null || true
cos_log_hook sync-task-current "set task=${TASK_ID}" 2>/dev/null || true
exit 0
