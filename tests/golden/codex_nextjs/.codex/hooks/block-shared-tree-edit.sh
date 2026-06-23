#!/usr/bin/env bash
# block-shared-tree-edit.sh — pr-mode edit isolation (companion to branch-guard).
#
# In COS_GIT_WORKFLOW=pr, a Write/Edit on a file inside the SHARED integration
# checkout (the main repo, not a worktree) is BLOCKED so every code change is
# isolated in a worktree — even work the user said not to make a board task for
# (`cos pr open --adhoc`). Inert in trunk mode (the default), so coding-os and
# every trunk consumer pay one env check and exit. Files inside a worktree, and
# files outside the repo entirely (scratch, dotfiles), pass.
# SPEC: docs/playbooks/pr-workflow.md § 5/§6.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

# Inert unless pr-mode — the common case, kept to a single comparison.
[[ "${COS_GIT_WORKFLOW:-trunk}" == "pr" ]] || exit 0

cos_require_parser block-shared-tree-edit

INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(printf '%s' "$INPUT" | cos_json_field tool_name)
case "$TOOL" in
  Write | Edit | MultiEdit) ;;
  *) exit 0 ;;
esac

FILE=$(printf '%s' "$INPUT" | cos_json_field tool_input.file_path)
[[ -z "$FILE" ]] && exit 0

# A file under a worktree root IS the isolation target — allow.
case "$FILE" in
  *"/.coding-os/worktrees/"*) exit 0 ;;
esac
if [[ -n "${COS_WORKTREE_ROOT:-}" && "$FILE" == "${COS_WORKTREE_ROOT}"/* ]]; then
  exit 0
fi

# Block only files inside the shared integration checkout = the main repo root
# (parent of COS_STATE_DIR). Edits elsewhere (scratch, ~/.config) pass through.
REPO_ROOT="$(cd -P "$(dirname "${COS_STATE_DIR}")" 2>/dev/null && pwd -P)" || REPO_ROOT=""
[[ -z "$REPO_ROOT" || "$REPO_ROOT" == "." ]] && exit 0

FILE_ABS="$FILE"
case "$FILE" in
  /*) ;;
  *) FILE_ABS="$(pwd)/$FILE" ;;
esac

if [[ "$FILE_ABS" == "${REPO_ROOT}/"* ]]; then
  cos_log_hook block-shared-tree-edit block "rule=pr-shared-tree-edit"
  bash "$(dirname "$0")/../scripts/log-write.sh" \
    --type "hook-block" --msg "block-shared-tree-edit" --what "$(basename "$FILE")" 2>/dev/null || true
  echo "BLOCKED (pr-mode): editing a file in the shared integration checkout." >&2
  echo "  Every change must be isolated in a worktree, never the shared tree." >&2
  echo "  To fix: 'cos pr open' (or 'cos pr open --adhoc' for no-task work)," >&2
  echo "  then edit inside the worktree." >&2
  echo "  See docs/playbooks/pr-workflow.md § 5/§6." >&2
  exit 2
fi
exit 0
