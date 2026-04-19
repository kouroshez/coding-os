#!/usr/bin/env bash
# PreToolUse hook: Block direct edits to protected files.
# Protected:
#   - changes.log (use make log-write)
#   - tasks.md status lines (use make task-done/task-start)
#   - Governance files: agent rules/, hooks/, CLAUDE.md, AGENTS.md,
#     infrastructure/scripts/ — never edit as side-effect of another task.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
OLD_STRING=$(echo "$INPUT" | jq -r '.tool_input.old_string // empty')

# Block direct edits to changes.log
if [[ "$FILE_PATH" == *"changes.log"* ]]; then
  echo "BLOCKED: Do not edit changes.log directly. Use 'make log-write TYPE=<type> MSG=\"title\" WHAT=\"impact\" FILES=\"files\"' or 'make task-done'." >&2
  exit 2
fi

# Block direct status changes in tasks.md (checkbox modifications)
if [[ "$FILE_PATH" == *"docs/tasks.md"* ]]; then
  if echo "$OLD_STRING" | grep -qE '^\- \[[ x/]\]'; then
    echo "BLOCKED: Do not change task status directly in tasks.md. Use 'make task-start TASK=<num>', 'make task-done TASK=<num> TYPE=<type> MSG=\"title\" WHAT=\"impact\" FILES=\"files\"', or 'make task-block TASK=<num> REASON=\"why\"'." >&2
    exit 2
  fi
fi

# Block edits to governance/workflow files unless explicitly tasked.
# These define HOW we work — changing them as a side-effect of another task
# can silently break workflow for all future sessions.
#
# Exception: paths inside templates/.../scaffold/ are SCAFFOLD TEMPLATES, not
# runtime state. They need to be writable so coding-os itself can ship updates
# to the scaffold (e.g. adding rag-config.yaml under .coding-os/ scaffold).
if [[ "$FILE_PATH" == *"/scaffold/"* ]]; then
  exit 0
fi

if [[ "$FILE_PATH" == *".claude/rules/"* ]] || \
   [[ "$FILE_PATH" == *".claude/hooks/"* ]] || \
   [[ "$FILE_PATH" == *".codex/hooks/"* ]] || \
   [[ "$FILE_PATH" == *".coding-os/"* ]] || \
   [[ "$FILE_PATH" == *"/CLAUDE.md" ]] || \
   [[ "$FILE_PATH" == *"/AGENTS.md" ]] || \
   [[ "$FILE_PATH" == *"infrastructure/scripts/"* ]]; then
  # Escape hatch: if the active task explicitly names governance work,
  # allow the edit. This prevents genuine docs/governance tasks from
  # being blocked by the safety net. The active task marker is session-
  # scoped and set via `make task-start` or write-state.sh.
  # Task marker lives in the agent-private state dir (COS_AGENT_DIR); when
  # cos-env.sh hasn't been sourced we fall back to the shared root.
  AGENT_DIR="${COS_AGENT_DIR:-${COS_STATE_DIR:-.coding-os}/${COS_AGENT:-unknown}}"
  TASK_FILE="$AGENT_DIR/.task-current"
  if [ -f "$TASK_FILE" ]; then
    TASK_VALUE=$(cat "$TASK_FILE" 2>/dev/null)
    # The task marker is "session-id value" — extract the value
    TASK_NAME="${TASK_VALUE##* }"
    # Allow when the task name clearly signals governance/docs work.
    case "$TASK_NAME" in
      *docs-update*|*docs-sync*|*governance*|*claude-md-update*|*agents-md-update*)
        exit 0
        ;;
    esac
  fi
  echo "BLOCKED: Governance/workflow file detected. Do not edit agent config dirs, CLAUDE.md, AGENTS.md, or infrastructure/scripts/ as a side-effect of another task. Create a dedicated task for governance changes, e.g. write-state.sh $AGENT_DIR/.task-current 'docs-update-...'" >&2
  exit 2
fi

exit 0
