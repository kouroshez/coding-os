#!/usr/bin/env bash
# enforce-task-transition.sh (Phase 0) — PreToolUse Write|Edit.
#
# BLOCKS hand-edits that mutate a task/audit STATUS transition
# (status: / **Status:** / checkbox [ ]->[x]) on docs/tasks/**/*.md —
# INCLUDING docs/tasks/audits/audit-*.md (unlike validate-task-frontmatter,
# which skips audits). Status transitions must route through cos_task_move /
# cos task-done / cos_supervise_record_output so the board DB, WIP caps, DoD
# gates, and the completion guardian stay consistent; a raw Edit bypasses all
# of them, and hand-ticking an audit evidence box defeats the Stop guardian.
#
# Allow-list: governance/docs-update/template-update active task, or
# COS_ALLOW_TASK_EDIT=1. Fail-open if jq/helper/python missing.
set -euo pipefail
source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook "enforce-task-transition" "entry" 2>/dev/null || true

# One-shot override (rare, legitimate large refactors of a task doc).
[[ "${COS_ALLOW_TASK_EDIT:-}" == "1" ]] && exit 0

payload="$(cos_read_stdin_bounded 5)"

file_path="$(printf '%s' "$payload" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")"

# Scope: only task/audit markdown (INCLUDES docs/tasks/audits/).
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
[[ -f "$HELPER" ]] || exit 0

if python3 "$HELPER" "$payload"; then
    exit_code=0
else
    exit_code=$?
fi
cos_log_hook "enforce-task-transition" "$([[ $exit_code -eq 0 ]] && echo allow || echo block)" 2>/dev/null || true
exit "$exit_code"
