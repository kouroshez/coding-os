#!/usr/bin/env bash
# cos commit-msg — enforce commit message contract for human/agent direct commits.
# Installed by: bash src/scripts/install-git-hooks.sh
# Defense-in-depth alongside PreToolUse Bash hook enforce-commit-message.sh —
# this layer fires for runtimes that don't honor PreToolUse hooks (Codex GUI, raw human).
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
# Meta-repo path first; fall back to a consumer's symlinked adapter hooks dir
# (.claude/.codex/.cursor) so the commit-message contract still fires in a
# `cos init` project, which has no src/core/ of its own (TASK-121). Mirrors
# the HOOKS_DIR resolution already in _pre_commit_body.sh.
HELPER="${REPO_ROOT}/src/core/hooks/_helpers/check_commit_message.py"
if [[ ! -f "$HELPER" ]]; then
  for _ad in .claude .codex .cursor; do
    _cand="${REPO_ROOT}/${_ad}/hooks/_helpers/check_commit_message.py"
    if [[ -f "$_cand" ]]; then HELPER="$_cand"; break; fi
  done
fi

if [[ ! -f "$HELPER" ]]; then
  exit 0
fi

if ! python3 "$HELPER" "$1" ; then
  echo "" >&2
  echo "Spec: src/core/rules/git-workflow.md § Commit Message Contract" >&2
  echo "Override (NOT recommended): git commit --no-verify ..." >&2
  exit 1
fi
exit 0
