#!/usr/bin/env bash
# PreToolUse hook: BLOCK Write/Edit on code files unless make task-start has been run.
# Session-scoped: only accepts task from the CURRENT session.
# Allows ad-hoc CLEAR fixes by checking thinking-os-gate classification.
set -euo pipefail

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')

if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')

# Only enforce for code files
if [[ "$FILE_PATH" != *.py ]] && [[ "$FILE_PATH" != *.ts ]] && [[ "$FILE_PATH" != *.tsx ]]; then
  exit 0
fi

# Skip test files, migrations, generated files, config files, hook scripts
if [[ "$FILE_PATH" == *test* ]] || [[ "$FILE_PATH" == *spec* ]] || [[ "$FILE_PATH" == *migrations* ]] || [[ "$FILE_PATH" == *node_modules* ]] || [[ "$FILE_PATH" == *__pycache__* ]] || [[ "$FILE_PATH" == *.claude/* ]] || [[ "$FILE_PATH" == *.coding-os/* ]]; then
  exit 0
fi

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

# Allow CLEAR 1 ad-hoc fixes without a task
source "$(dirname "$0")/check-state.sh"
check_state "${COS_AGENT_DIR}/.thinking-os-gate" 7200
if [[ "$STATE_VALID" == "true" ]]; then
  CLASSIFICATION=$(echo "$STATE_VALUE" | awk '{print $1}')
  DIMS=$(echo "$STATE_VALUE" | awk '{print $2}')
  if [[ "$CLASSIFICATION" == "CLEAR" ]] && [[ "$DIMS" == "1" ]]; then
    exit 0
  fi
fi

# Check task-current (session-scoped, 8h timeout)
check_state "${COS_AGENT_DIR}/.task-current" 28800

if [[ "$STATE_VALID" != "true" ]]; then
  echo "BLOCKED: No active task for this session. Reason: $STATE_REASON" >&2
  echo "  bash .claude/hooks/write-state.sh ${COS_AGENT_DIR}/.task-current \"<task-name>\"" >&2
  echo "  For trivial fixes: bash .claude/hooks/write-state.sh ${COS_AGENT_DIR}/.thinking-os-gate \"CLEAR 1\"" >&2
  exit 2
fi

exit 0
