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

# Fast-path: this hook only validates `git commit` messages. If the raw payload
# never mentions "git commit" there is nothing to check — bail before any jq
# spawn (this hook fires on EVERY Bash command).
case "$INPUT" in
  *"git commit"*) ;;
  *) exit 0 ;;
esac

TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
[[ "$TOOL" != "Bash" ]] && exit 0

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")
echo "$COMMAND" | grep -qE 'git[[:space:]]+commit\b' || exit 0

# Resolve _helpers/ through the hook's PHYSICAL location so it works through the
# .claude/hooks/ symlinks consumer projects install — there .claude/hooks/_helpers
# does not exist (install symlinks each .sh, never the subdir) and the consumer has
# no src/core/ tree, so the old "$(dirname "$0")/_helpers" + src/core fallback both
# missed and the index.lock wait AND the commit-message contract silently no-op'd.
# Mirrors the resolution dance in branch-guard.sh.
_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
  _dir="$(cd -P "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ "$_src" != /* ]] && _src="${_dir}/${_src}"
done
HELPERS_DIR="$(cd -P "$(dirname "$_src")" && pwd)/_helpers"
unset _src _dir

# Pre-emptively wait out a concurrent commit's index.lock so this commit does
# not fail under multi-agent contention. Fail-open by contract.
_GIL="${HELPERS_DIR}/git_index_lock.sh"
# shellcheck source=/dev/null
[[ -f "$_GIL" ]] && source "$_GIL" 2>/dev/null && cos_wait_for_git_index_lock || true

cos_log_hook enforce-commit-message fire
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

if ! CHECK_OUT=$(printf '%s' "$MSG" | python3 "$CHECK" - 2>&1); then
  echo "BLOCKED: git log is permanent and release-please parses the title into CHANGELOG.md — a malformed message corrupts the changelog forever." >&2
  printf '%s\n' "$CHECK_OUT" >&2
  cos_log_hook enforce-commit-message block "rule=commit-msg-contract"
  exit 2
fi

cos_log_hook enforce-commit-message ok
exit 0
