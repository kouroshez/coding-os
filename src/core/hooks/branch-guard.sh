#!/usr/bin/env bash
# branch-guard.sh (Phase gate) — enforce trunk-based git integrity.
#
# PreToolUse:Bash hook. In trunk mode (default) it BLOCKs commands that
# either (a) create a branch / worktree or (b) rewrite shared HEAD —
# both classes can clobber a peer session's commits or scatter work
# across phantom branches. The coding-os workflow commits directly to
# main (see src/core/rules/git-workflow.md). Set COS_GIT_WORKFLOW=pr to
# allow branches / HEAD-moves (future multi-developer mode).
#
# The actual parsing lives in _helpers/branch_guard_check.py — it
# handles whitespace normalization, `git -C` / `git -c` global options,
# nested `sh -c "..."` / `bash -c "..."`, command-segment splitting,
# and `shlex` quoting (so literal `git reset HEAD~1` inside an `echo`
# or `grep` arg does NOT trigger). This script is a thin wrapper:
# fast-skip when "git" isn't in the command, otherwise dispatch to the
# helper and act on its JSON verdict.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
if [[ "$TOOL" != "Bash" ]]; then
  exit 0
fi

# pr mode = branches + HEAD-moves allowed; the seam for future team workflows.
if [[ "${COS_GIT_WORKFLOW:-trunk}" == "pr" ]]; then
  exit 0
fi

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")
[[ -z "$COMMAND" ]] && exit 0

# Fast-skip: no "git" substring → no risk; skip the python startup cost.
if [[ "$COMMAND" != *git* ]]; then
  exit 0
fi

cos_log_hook branch-guard fire "tool=Bash"

# Resolve the helper through the file's physical location — works through
# the .claude/hooks/ symlinks that consumer projects install.
_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
  _dir="$(cd -P "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ "$_src" != /* ]] && _src="${_dir}/${_src}"
done
HOOKS_PHYS_DIR="$(cd -P "$(dirname "$_src")" && pwd)"
unset _src _dir
HELPER="${HOOKS_PHYS_DIR}/_helpers/branch_guard_check.py"

if [[ ! -f "$HELPER" ]]; then
  # Fail-open if the helper is missing — better to under-enforce than to
  # silently break every Bash call.
  cos_log_hook branch-guard ok "reason=helper-missing"
  exit 0
fi

# Run the helper with a short timeout — python3 cold-start on macOS is
# ~50-150ms; the parser itself is microseconds. 5s is generous.
VERDICT_JSON=$(printf '%s' "$INPUT" | python3 "$HELPER" 2>/dev/null || echo '{"verdict":"allow"}')
VERDICT=$(echo "$VERDICT_JSON" | jq -r '.verdict // "allow"' 2>/dev/null || echo "allow")

if [[ "$VERDICT" != "block" ]]; then
  cos_log_hook branch-guard ok || true
  exit 0
fi

REASON=$(echo "$VERDICT_JSON" | jq -r '.reason // "branch-guard-block"' 2>/dev/null)
MESSAGE=$(echo "$VERDICT_JSON" | jq -r '.message // ""' 2>/dev/null)

cos_log_hook branch-guard block "rule=${REASON}"
bash "$(dirname "$0")/../scripts/log-write.sh" \
  --type "hook-block" --msg "branch-guard" --what "$REASON" 2>/dev/null || true

if [[ -n "$MESSAGE" ]]; then
  printf '%s\n' "$MESSAGE" >&2
else
  echo "BLOCKED: coding-os trunk-based git workflow forbids this command." >&2
  echo "  See src/core/rules/git-workflow.md. Override: COS_GIT_WORKFLOW=pr." >&2
fi
exit 2
