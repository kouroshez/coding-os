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

FAILED=0
echo "cos pre-commit: checking $(echo "$STAGED_FILES" | wc -l | tr -d ' ') staged file(s)..."

_check_hook() {
  local HOOK_SCRIPT="$1"
  local FILE="$2"
  local LABEL="$3"
  [[ ! -f "${HOOKS_DIR}/${HOOK_SCRIPT}" ]] && return 0
  local ABS_PATH="${REPO_ROOT}/${FILE}"
  [[ ! -f "$ABS_PATH" ]] && return 0
  local FAKE_INPUT
  FAKE_INPUT=$(python3 -c "
import json, sys
abs_path = sys.argv[1]
file_path = sys.argv[2]
try:
    with open(abs_path, 'r', errors='replace') as f:
        content = f.read()
except Exception:
    content = ''
print(json.dumps({'tool_name':'Write','tool_input':{'file_path':file_path,'content':content,'new_string':content}}))
" "$ABS_PATH" "$FILE" 2>/dev/null || true)
  [[ -z "$FAKE_INPUT" ]] && return 0
  local OUT
  local CODE=0
  OUT=$(echo "$FAKE_INPUT" | bash "${HOOKS_DIR}/${HOOK_SCRIPT}" 2>&1) || CODE=$?
  if [[ "$CODE" == "2" ]]; then
    echo "BLOCKED [${LABEL}] ${FILE}:" >&2
    echo "${OUT}" >&2
    FAILED=1
  fi
}

while IFS= read -r FILE; do
  [[ -z "$FILE" ]] && continue
  _check_hook "block-bad-patterns.sh" "$FILE" "bad-patterns"
  _check_hook "block-migration-conflict.sh" "$FILE" "migration-conflict"
done <<< "$STAGED_FILES"

TASK_FILES=$(echo "$STAGED_FILES" | grep "^docs/tasks/TASK-" 2>/dev/null || true)
if [[ -n "$TASK_FILES" ]]; then
  while IFS= read -r FILE; do
    [[ -z "$FILE" ]] && continue
    _check_hook "validate-task-frontmatter.sh" "$FILE" "task-frontmatter"
  done <<< "$TASK_FILES"
fi

if [[ "$FAILED" == "1" ]]; then
  echo "" >&2
  echo "cos pre-commit: commit blocked. Fix the issues above and re-stage." >&2
  echo "To skip (NOT recommended): git commit --no-verify" >&2
  exit 1
fi

echo "cos pre-commit: OK"
exit 0
