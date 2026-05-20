#!/usr/bin/env bash
# cos pre-commit — critical validation for human direct edits.
# Installed by: bash scripts/install-git-hooks.sh
# Covers the enforcement gap where a human editing files directly bypasses
# ALL PreToolUse:Write|Edit hooks.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOKS_DIR="${REPO_ROOT}/src/core/hooks"

if [[ ! -d "$HOOKS_DIR" && -d "${REPO_ROOT}/core/hooks" ]]; then
  HOOKS_DIR="${REPO_ROOT}/core/hooks"
fi
if [[ -d "${REPO_ROOT}/.claude/hooks" ]]; then
  HOOKS_DIR="${REPO_ROOT}/.claude/hooks"
fi

source "${HOOKS_DIR}/cos-env.sh" 2>/dev/null || true

STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null || true)

if [[ -z "$STAGED_FILES" ]]; then
  exit 0
fi

FILE_COUNT=$(echo "$STAGED_FILES" | wc -l | tr -d ' ')
echo "cos pre-commit: checking ${FILE_COUNT} staged file(s)..."

# Delegate the per-file iteration to a single Python helper. The previous
# bash-loop implementation (even with mktemp IPC) deadlocks git-commit's
# hook environment beyond ~15 staged files — bash 5.x fork-bombs and
# loses pipe synchronization. The Python helper does the same work in
# one process: no nested subshells, no per-file fork-bomb.
BATCH_HELPER="${HOOKS_DIR}/_helpers/pre_commit_batch.py"
if [[ ! -f "$BATCH_HELPER" ]]; then
  BATCH_HELPER="${REPO_ROOT}/src/core/hooks/_helpers/pre_commit_batch.py"
fi

if [[ ! -f "$BATCH_HELPER" ]]; then
  echo "cos pre-commit: WARNING — batch helper missing; skipping hook scan." >&2
  echo "  expected at: $BATCH_HELPER" >&2
  exit 0
fi

# Pass file list as positional args (one per arg, no shell-word splits).
FILE_ARGS=()
while IFS= read -r FILE; do
  [[ -z "$FILE" ]] && continue
  FILE_ARGS+=("$FILE")
done <<< "$STAGED_FILES"

if python3 "$BATCH_HELPER" "$HOOKS_DIR" "$REPO_ROOT" "${FILE_ARGS[@]}"; then
  echo "cos pre-commit: OK"
  exit 0
else
  echo "" >&2
  echo "cos pre-commit: commit blocked. Fix the issues above and re-stage." >&2
  echo "To skip (NOT recommended): git commit --no-verify" >&2
  exit 1
fi
