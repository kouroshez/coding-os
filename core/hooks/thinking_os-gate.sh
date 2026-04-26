#!/usr/bin/env bash
# PreToolUse hook: BLOCK Write/Edit on code files until Complexity Gate is recorded.
# Session-scoped: only accepts gate from the CURRENT session.
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

# Skip test files, migrations, generated files, config files
if [[ "$FILE_PATH" == *test* ]] || [[ "$FILE_PATH" == *spec* ]] || [[ "$FILE_PATH" == *migrations* ]] || [[ "$FILE_PATH" == *node_modules* ]] || [[ "$FILE_PATH" == *__pycache__* ]]; then
  exit 0
fi

if [[ "$FILE_PATH" == *.thinking_os-gate ]]; then
  exit 0
fi

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
GATE_FILE="${COS_AGENT_DIR}/.thinking_os-gate"

# Use session-scoped check
source "$(dirname "$0")/check-state.sh"
check_state "$GATE_FILE" 7200  # 120 min

if [[ "$STATE_VALID" != "true" ]]; then
  echo "BLOCKED: Thinking OS Complexity Gate not valid. Reason: $STATE_REASON" >&2
  echo "Record gate: bash .claude/hooks/write-state.sh ${COS_AGENT_DIR}/.thinking_os-gate \"CLEAR 1\"" >&2
  echo '  (or COMPLICATED/COMPLEX with dimension count)' >&2
  exit 2
fi

# Validate classification
CLASSIFICATION=$(echo "$STATE_VALUE" | awk '{print $1}')
if [[ "$CLASSIFICATION" != "CLEAR" ]] && [[ "$CLASSIFICATION" != "COMPLICATED" ]] && [[ "$CLASSIFICATION" != "COMPLEX" ]] && [[ "$CLASSIFICATION" != "CHAOTIC" ]]; then
  echo "BLOCKED: Invalid classification '$CLASSIFICATION'. Must be CLEAR, COMPLICATED, COMPLEX, or CHAOTIC." >&2
  exit 2
fi

exit 0
