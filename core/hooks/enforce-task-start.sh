#!/usr/bin/env bash
# PreToolUse hook: BLOCK Write/Edit on code files unless make task-start has been run.
# Session-scoped: only accepts task from the CURRENT session.
# Allows ad-hoc CLEAR fixes by checking thinking_os-gate classification.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

INPUT="$(cos_read_stdin_bounded 2)"
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


# Allow CLEAR 1 ad-hoc fixes without a task
source "$(dirname "$0")/check-state.sh"
check_state "${COS_AGENT_DIR}/.thinking_os-gate" 7200
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
  echo "  Preferred:  cos task-create --title \"...\" --swimlane <domain> --kind <type>" >&2
  echo "              cos task-start TASK-NNN" >&2
  echo "  Manual:     bash \"\$COS_AGENT_DIR/hooks/write-state.sh\" \"\$COS_AGENT_DIR/.task-current\" \"<task-name>\"" >&2
  echo "  Trivial:    bash \"\$COS_AGENT_DIR/hooks/write-state.sh\" \"\$COS_AGENT_DIR/.thinking_os-gate\" \"CLEAR 1\"" >&2
  exit 2
fi

# Phase M advisory: warn if .persona is missing on COMPLICATED+ tasks.
# task-start.sh populates .persona automatically; absence means the task
# was started before M.4 or the persona resolver failed silently.
if [[ ! -f "${COS_AGENT_DIR}/.persona" ]]; then
  GATE_CLASSIFICATION=$(echo "${STATE_VALUE:-}" | awk '{print $1}')
  if [[ "$GATE_CLASSIFICATION" == "COMPLICATED" || "$GATE_CLASSIFICATION" == "COMPLEX" ]]; then
    echo "[Phase M] Advisory: No persona marker found for this COMPLICATED/COMPLEX task." >&2
    echo "  Re-run \`make task-start TASK=<N>\` to trigger persona routing, or set manually:" >&2
    echo "  echo 'senior-backend' > ${COS_AGENT_DIR}/.persona" >&2
  fi
fi

exit 0
