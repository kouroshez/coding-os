#!/usr/bin/env bash
# branch-guard.sh (Phase gate) — enforce trunk-based git workflow.
#
# PreToolUse:Bash hook. In trunk mode (default) it BLOCKs any command
# that creates a git branch or worktree — the coding-os workflow commits
# directly to main (see src/core/rules/git-workflow.md). Set
# COS_GIT_WORKFLOW=pr to allow branches (future multi-developer mode).
# Fail-closed: a creation command is blocked. List/delete/rename/checkout
# of existing branches is always allowed.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
if [[ "$TOOL" != "Bash" ]]; then
  exit 0
fi

# pr mode = branches allowed; the seam for future team workflows.
if [[ "${COS_GIT_WORKFLOW:-trunk}" == "pr" ]]; then
  exit 0
fi

COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")
[[ -z "$COMMAND" ]] && exit 0

cos_log_hook branch-guard fire "tool=Bash"

REASON=""
# git checkout -b / -B  ·  git switch -c / -C  → branch creation.
if echo "$COMMAND" | grep -qE 'git +(checkout|switch) +.*-[bBcC]\b'; then
  REASON="branch-create-checkout"
# git branch <name>  (first token after `branch` is a name, not a flag).
elif echo "$COMMAND" | grep -qE 'git +branch +[A-Za-z0-9._/]'; then
  REASON="branch-create"
# git worktree add  → trunk mode does not use worktrees.
elif echo "$COMMAND" | grep -qE 'git +worktree +add\b'; then
  REASON="worktree-add"
fi

if [[ -n "$REASON" ]]; then
  cos_log_hook branch-guard block "rule=${REASON}"
  bash "$(dirname "$0")/../scripts/log-write.sh" \
    --type "hook-block" --msg "branch-guard" --what "$REASON" 2>/dev/null || true
  {
    echo "BLOCKED: coding-os uses a trunk-based git workflow — commit"
    echo "directly to main, do not create branches or worktrees."
    echo ""
    echo "  Why: feature branches lingered unmerged and tangled across"
    echo "  concurrent sessions. See src/core/rules/git-workflow.md."
    echo ""
    echo "  To fix: edit files, then 'git commit <explicit paths>' and"
    echo "  'git pull --rebase origin main && git push origin main'."
    echo ""
    echo "  If the USER explicitly asked for a branch, re-run with"
    echo "  COS_GIT_WORKFLOW=pr set for that command."
  } >&2
  exit 2
fi

cos_log_hook branch-guard ok || true
exit 0
