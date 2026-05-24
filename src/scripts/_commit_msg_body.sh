#!/usr/bin/env bash
# cos commit-msg — enforce commit message contract for human/agent direct commits.
# Installed by: bash src/scripts/install-git-hooks.sh
# Defense-in-depth alongside PreToolUse Bash hook enforce-commit-message.sh —
# this layer fires for runtimes that don't honor PreToolUse hooks (Codex GUI, raw human).
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HELPER="${REPO_ROOT}/src/core/hooks/_helpers/check_commit_message.py"

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
