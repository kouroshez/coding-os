#!/usr/bin/env bash
# enforce-task-transition.sh — PreToolUse Write|Edit.
#
# BLOCKS hand-edits that mutate a task STATUS transition
# (status: / **Status:** / checkbox [ ]->[x]) on docs/tasks/**/*.md.
# Status transitions must route through cos_task_move / cos task-done so the
# board DB, WIP caps, and DoD gates stay consistent; a raw Edit bypasses all
# of them.
#
# Allow-list: governance/docs-update/template-update active task, or
# COS_ALLOW_TASK_EDIT=1. Fail-closed when the detection helper is missing
# (COS_ALLOW_TASK_EDIT=1 escapes).
set -euo pipefail
source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook "enforce-task-transition" "entry" 2>/dev/null || true

# One-shot override (rare, legitimate large refactors of a task doc).
[[ "${COS_ALLOW_TASK_EDIT:-}" == "1" ]] && exit 0

# Fail-closed: a status-transition guard (Rule 25 trust boundary) that cannot
# read the edit must DENY (observability-eye I8). The override above bypasses it.
cos_require_parser enforce-task-transition

payload="$(cos_read_stdin_bounded 5)"

file_path="$(printf '%s' "$payload" | cos_json_field tool_input.file_path)"

# Scope: only task markdown under docs/tasks/.
if [[ -z "$file_path" ]] || [[ "$file_path" != *"docs/tasks/"*.md ]]; then
    exit 0
fi

# Governance allow-list — panel-scoped, session+freshness aware.
source "$(dirname "$0")/check-state.sh" 2>/dev/null || true
if type check_state >/dev/null 2>&1; then
    check_state "${COS_PANEL_DIR:-$COS_AGENT_DIR}/.task-current" 28800 2>/dev/null || true
    case "${STATE_VALUE:-}" in
        *governance*|*docs-update*|*template-update*) exit 0 ;;
    esac
fi

# Mutation detection — delegate to helper (Rule 8: no python heredoc).
# Resolve the physical hooks dir through the .claude/hooks symlink.
_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
    _dir="$(cd -P "$(dirname "$_src")" && pwd)"
    _src="$(readlink "$_src")"
    [[ "$_src" != /* ]] && _src="$_dir/$_src"
done
HSRC="$(cd -P "$(dirname "$_src")" && pwd)"
unset _src _dir
HELPER="${HSRC}/_helpers/detect_status_transition.py"
if [[ ! -f "$HELPER" ]]; then
  # Fail-CLOSED: cannot tell a status hand-edit from a body edit without the
  # helper, so deny the task-md write rather than let a forged status through
  # (Rule 25 / observability-eye I8/A2). Escape: COS_ALLOW_TASK_EDIT=1.
  cos_say error hook.enforce_task_transition "detect_status_transition helper missing — failing closed on task-md edit" 2>/dev/null || true
  cos_log_hook "enforce-task-transition" "block" "rule=helper-missing" 2>/dev/null || true
  echo "BLOCKED: enforce-task-transition helper missing ($HELPER) — cannot verify this task edit; failing closed." >&2
  echo "  Restore src/core/hooks/_helpers/detect_status_transition.py, or set COS_ALLOW_TASK_EDIT=1 for a one-shot bypass." >&2
  exit 2
fi

if python3 "$HELPER" "$payload"; then
    exit_code=0
else
    exit_code=$?
fi
cos_log_hook "enforce-task-transition" "$([[ $exit_code -eq 0 ]] && echo allow || echo block)" 2>/dev/null || true
exit "$exit_code"
