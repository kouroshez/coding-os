#!/usr/bin/env bash
# PreToolUse hook: BLOCK Write/Edit on code files for COMPLICATED/COMPLEX tasks
# unless a Zoom checkpoint (Problem Framing) has been recorded.
# Session-scoped: only accepts checkpoints from the CURRENT session.
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
GATE_FILE="${COS_AGENT_DIR}/.thinking-os-gate"
ZOOM_FILE="${COS_AGENT_DIR}/.zoom-checkpoint"

# Only enforce for COMPLICATED and COMPLEX
source "$(dirname "$0")/check-state.sh"
check_state "$GATE_FILE" 7200

if [[ "$STATE_VALID" != "true" ]]; then
  exit 0  # No gate = thinking-os-gate.sh will handle it
fi

CLASSIFICATION=$(echo "$STATE_VALUE" | awk '{print $1}')

if [[ "$CLASSIFICATION" == "CLEAR" ]] || [[ "$CLASSIFICATION" == "CHAOTIC" ]]; then
  exit 0
fi

# COMPLICATED or COMPLEX: require zoom checkpoint (session-scoped)
check_state "$ZOOM_FILE" 7200

if [[ "$STATE_VALID" != "true" ]]; then
  echo "BLOCKED: Task classified as $CLASSIFICATION but no Plan checkpoint for this session." >&2
  echo "Reason: $STATE_REASON" >&2
  echo "Record checkpoint: bash .claude/hooks/write-state.sh ${COS_AGENT_DIR}/.zoom-checkpoint \"PROBLEM_FRAMED\"" >&2
  exit 2
fi

exit 0
