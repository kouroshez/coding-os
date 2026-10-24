#!/usr/bin/env bash
# PreToolUse hook: BLOCK Edit/Write on docs/tasks/TASK-*.md when the
# proposed body fails Definition-of-Ready or Definition-of-Done for
# the task's kind.
#
# Single SSOT (transition-gates.yaml). All real logic
# lives in src/core/board_os/transition_gates_cli.py; this hook just
# pipes the Claude Code payload to that CLI.
#
# Override (audited): COS_DOR_OVERRIDE=1 COS_OVERRIDE_REASON="...≥15 chars"
#                     COS_VERIFY_OVERRIDE=1 COS_OVERRIDE_REASON="..."
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi


INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")

# Only intercept Edit/Write on TASK-*.md files.
if [[ "$TOOL" != "Edit" && "$TOOL" != "Write" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
case "$FILE_PATH" in
  *docs/tasks/TASK-*.md) : ;;
  *) exit 0 ;;
esac

PROJECT_ROOT="${COS_PROJECT_ROOT:-$(pwd)}"
cd "$PROJECT_ROOT" || exit 0

# The CLI handles missing pydantic/yaml gracefully (returns pass + warn) so a
# stripped environment never hard-blocks.
cos_core_pyrun "$PROJECT_ROOT"

set +e
echo "$INPUT" | "${PYRUN[@]}" -m core.board_os.transition_gates_cli check-payload
EXIT_CODE=$?
set -e

case "$EXIT_CODE" in
  0) OUTCOME=allow ;;
  2) OUTCOME=block ;;
  *) OUTCOME=error ;;
esac
cos_log_hook "enforce-task-body" "$OUTCOME" 2>/dev/null || true
exit "$EXIT_CODE"
