#!/usr/bin/env bash
# nudge-task-discovery.sh — steer task lookup to the board, not raw files.
#
# Three events, all fail-open (exit 0), debounced once per session per leg:
#   UserPromptSubmit: task-reference intent (TASK-NNN, check/show/look-at
#     task; bilingual EN + Persian) -> additionalContext recommending
#     `cos task-show TASK-NNN` / cos_task_search / cos_task_show (MCP).
#   PreToolUse Bash:  command reads docs/tasks/ directly (ls/grep/cat/find/
#     head/tail/awk/sed/less/more/bat/rg/wc/nl/tac) -> stderr warning.
#   PreToolUse Read:  Read tool targets a docs/tasks/** path -> stderr warning
#     recommending cos task-show over a raw file Read.
#
# Closes the screenshot-2 gap: agent ran `ls docs/tasks | grep 058` + raw
# Read instead of cos task-show. Mirrors nudge-graph-os.sh mechanism.
set -euo pipefail
source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"

# Fast-path: every leg keys on either a "docs/tasks" path (Bash/Read) or the
# word "task" in a prompt (UserPromptSubmit task-reference intent). If the raw
# payload contains neither there is nothing to nudge — bail before any jq spawn
# (fires on EVERY Bash command and every prompt). Superset of all real triggers.
case "$INPUT" in
  *docs/tasks*|*task*) ;;
  *) exit 0 ;;
esac

TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")

MARKER_DIR="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.task-nudge"  # panel-first: cleared at panel scope each SessionStart
mkdir -p "$MARKER_DIR" 2>/dev/null || true

# ---- PreToolUse Read leg ----
# A raw Read of docs/tasks/** bypasses the board exactly like ls/grep does.
# cos task-show / cos_task_search are MCP/CLI calls, never the Read tool, so
# this leg only ever sees genuine file Reads.
if [[ "$TOOL" == "Read" ]]; then
  FP=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
  [[ -z "$FP" ]] && exit 0
  if [[ "$FP" == *"docs/tasks/"* ]]; then
    RM="${MARKER_DIR}/read"
    [[ -f "$RM" ]] && exit 0
    touch "$RM" 2>/dev/null || true
    cos_log_hook nudge-task-discovery fire "leg=read" 2>/dev/null || true
    echo "warning: [task nudge] Read of docs/tasks/ directly — prefer 'cos task-show TASK-NNN' (or cos_task_search) for a board-aware read instead of a raw file Read." >&2
  fi
  exit 0
fi

# ---- PreToolUse Bash leg ----
if [[ "$TOOL" == "Bash" ]]; then
  CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")
  [[ -z "$CMD" ]] && exit 0
  # Match a file-reading command targeting docs/tasks. cos task-show /
  # cos_task_search contain no "docs/tasks" literal, so they never match.
  # Broadened reader set — awk/sed/less/more/bat/rg/wc/nl/tac.
  if printf '%s' "$CMD" | grep -qE '(ls|grep|cat|find|head|tail|awk|sed|less|more|bat|rg|wc|nl|tac)[^|;&]*docs/tasks' 2>/dev/null; then
    BM="${MARKER_DIR}/bash"
    [[ -f "$BM" ]] && exit 0
    touch "$BM" 2>/dev/null || true
    cos_log_hook nudge-task-discovery fire "leg=bash" 2>/dev/null || true
    echo "warning: [task nudge] reading docs/tasks/ directly — prefer 'cos task-show TASK-NNN' (or cos_task_search) for a board-aware read instead of file hunting." >&2
  fi
  exit 0
fi

# ---- UserPromptSubmit leg ----
PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty' 2>/dev/null || echo "")
[[ ${#PROMPT} -lt 15 ]] && exit 0
PL=$(printf '%s' "$PROMPT" | tr '[:upper:]' '[:lower:]')
if printf '%s' "$PL" | grep -qE '\btask-[0-9]+\b|check task|show task|look at task|open task|status of task' 2>/dev/null; then
  PM="${MARKER_DIR}/prompt"
  [[ -f "$PM" ]] && exit 0
  touch "$PM" 2>/dev/null || true
  cos_log_hook nudge-task-discovery fire "leg=prompt" 2>/dev/null || true
  CONTEXT="[task nudge] Task reference detected — run \`cos task-show TASK-NNN\` (or cos_task_search if no ID; cos_task_show via MCP in-session) instead of ls/grep/cat on docs/tasks/. Tasks are the third retrieval layer (Rule 18 reconciliation)."
  printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":$(printf '%s' "$CONTEXT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}"
fi
exit 0
