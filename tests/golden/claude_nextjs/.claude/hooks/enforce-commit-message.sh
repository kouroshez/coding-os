#!/usr/bin/env bash
# enforce-commit-message.sh — block `git commit -m` with non-compliant message.
#
# PreToolUse:Bash matcher. Best-effort extracts -m "..." / -m '...' content via
# _helpers/extract_commit_msg_arg.py, then validates with check_commit_message.py.
# Heredoc / multi-line forms the regex can't parse defer to the git commit-msg
# hook installed via src/scripts/install-git-hooks.sh (defense-in-depth).
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
[[ "$TOOL" != "Bash" ]] && exit 0

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")
echo "$COMMAND" | grep -qE 'git[[:space:]]+commit\b' || exit 0

# Pre-emptively wait out a concurrent commit's index.lock so this commit does
# not fail under multi-agent contention (TASK-170). Fail-open by contract.
_GIL="$(dirname "$0")/_helpers/git_index_lock.sh"
[[ -f "$_GIL" ]] || _GIL="$(git rev-parse --show-toplevel 2>/dev/null)/src/core/hooks/_helpers/git_index_lock.sh"
# shellcheck source=/dev/null
[[ -f "$_GIL" ]] && source "$_GIL" 2>/dev/null && cos_wait_for_git_index_lock || true

cos_log_hook enforce-commit-message fire

HELPERS_DIR="$(dirname "$0")/_helpers"
if [[ ! -d "$HELPERS_DIR" ]]; then
  REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
  HELPERS_DIR="${REPO_ROOT}/src/core/hooks/_helpers"
fi
EXTRACT="${HELPERS_DIR}/extract_commit_msg_arg.py"
CHECK="${HELPERS_DIR}/check_commit_message.py"
if [[ ! -f "$EXTRACT" || ! -f "$CHECK" ]]; then
  echo "warning: enforce-commit-message: helpers missing; skipping" >&2
  exit 0
fi

MSG=$(printf '%s' "$COMMAND" | python3 "$EXTRACT")

if [[ -z "$MSG" ]]; then
  cos_log_hook enforce-commit-message skip "reason=cannot-parse-defer-to-git-hook"
  exit 0
fi

if ! printf '%s' "$MSG" | python3 "$CHECK" - ; then
  cos_log_hook enforce-commit-message block "rule=commit-msg-contract"
  exit 2
fi

cos_log_hook enforce-commit-message ok
exit 0
