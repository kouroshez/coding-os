#!/usr/bin/env bash
# PreToolUse hook: BLOCK Write/Edit on code files unless this session's task is in_progress.
# A CLEAR 1 gate excuses a trivial edit, except when the turn asked for implementation
# or governance work. Contract: docs/engineering/task-mode-matrix.md.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
# Fail-open if project state is incomplete (fresh clone, mid-init, wrong cwd).
cos_sanity_check enforce-task-start state_dir 2>/dev/null || true

INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(printf '%s' "$INPUT" | cos_json_field tool_name)

if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
  exit 0
fi

FILE_PATH=$(printf '%s' "$INPUT" | cos_json_field tool_input.file_path)

source "$(dirname "$0")/check-state.sh"

# Code = built-in extensions + `.coding-os.yaml` code_extensions. Tests are code
# too: writing them is part of the task's work.
cos_is_code_file "$FILE_PATH" || exit 0
case "$FILE_PATH" in
  *migrations*|*node_modules*|*__pycache__*|*.claude/*|*.codex/*|*.coding-os/*) exit 0 ;;
esac

# The mode only decides whether a CLEAR 1 gate may excuse the edit; it never
# switches enforcement off (task-mode-matrix.md § Task enforcement is not a mode
# decision). `system` is the hook-internal bypass.
TASK_MODE="$(cos_task_mode)"
[[ "$TASK_MODE" == "system" ]] && exit 0

if ! cos_active_task; then
  _bound_id="$ACTIVE_TASK_ID"
  _bound_status="$ACTIVE_TASK_STATUS"
  _bound_reason="${STATE_REASON:-}"
  if cos_clear1_escape; then
    cos_log_hook enforce-task-start allow "clear1 mode=${TASK_MODE:-none}" 2>/dev/null || true
    exit 0
  fi
  if [[ -n "$_bound_id" ]]; then
    echo "BLOCKED: ${_bound_id} is ${_bound_status}, not in_progress; code edits run under an in_progress task." >&2
    echo "  Rework on it:   cos task-move ${_bound_id} --to in_progress" >&2
    echo "  Next work:      cos task-create ... then cos task-start TASK-NNN" >&2
  else
    echo "BLOCKED: No in_progress task is bound to this session${_bound_reason:+ (${_bound_reason})}." >&2
    echo "  Preferred:  cos task-create --title \"...\" --swimlane <lane> --kind <type> --acceptance \"Given ..., When ..., Then ...\" --ready" >&2
    echo "              cos task-start TASK-NNN" >&2
  fi
  case "$TASK_MODE" in
    propose-formal|gov-required)
      echo "  This turn asked for implementation or governance work (mode=${TASK_MODE}), so a CLEAR 1 gate does not apply." >&2 ;;
    *)
      echo "  Trivial edit only: record a CLEAR 1 gate with cos_classify_prompt (shell fallback: write-state.sh .thinking_os-gate \"CLEAR 1 <why>\")." >&2 ;;
  esac
  cos_log_hook enforce-task-start block "mode=${TASK_MODE:-none} task=${_bound_id:-none}" 2>/dev/null || true
  exit 2
fi

# Advisory: warn if .persona is missing on COMPLICATED+ tasks.
# Persona routing populates .persona when the task starts; absence means the task
# was started before M.4 or the persona resolver failed silently.
if [[ ! -f "${COS_AGENT_DIR}/.persona" ]]; then
  GATE_CLASSIFICATION=$(echo "${STATE_VALUE:-}" | awk '{print $1}')
  if [[ "$GATE_CLASSIFICATION" == "COMPLICATED" || "$GATE_CLASSIFICATION" == "COMPLEX" ]]; then
    echo "Advisory: No persona marker found for this COMPLICATED/COMPLEX task." >&2
    echo "  Re-run \`cos task-start TASK-NNN\` to trigger persona routing, or set manually:" >&2
    echo "  echo 'senior-backend' > ${COS_AGENT_DIR}/.persona" >&2
  fi
fi

exit 0
