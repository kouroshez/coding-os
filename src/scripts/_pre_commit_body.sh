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

# Locate the JSON-envelope helper. Extracted to a stand-alone script so
# bash 5.3.9 does NOT deadlock on $(python3 -c '<multiline>') — see
# Rule 8 in docs/governance/critical-rules.md.
HELPER="${HOOKS_DIR}/_helpers/pre_commit_fake_input.py"
if [[ ! -f "$HELPER" ]]; then
  # Fallback: try repo-rooted path when HOOKS_DIR points at .claude/hooks
  # (an adapter dir without the _helpers/ tree).
  HELPER="${REPO_ROOT}/src/core/hooks/_helpers/pre_commit_fake_input.py"
fi

_check_hook() {
  local HOOK_SCRIPT="$1"
  local FILE="$2"
  local LABEL="$3"
  [[ ! -f "${HOOKS_DIR}/${HOOK_SCRIPT}" ]] && return 0
  local ABS_PATH="${REPO_ROOT}/${FILE}"
  [[ ! -f "$ABS_PATH" ]] && return 0
  [[ ! -f "$HELPER" ]] && return 0
  # Pass the JSON envelope via a temp file (mktemp) instead of nested
  # pipes inside command substitution. Bash 5.x has been observed to
  # deadlock on $(echo "$X" | bash hook 2>&1) when invoked under
  # git-commit's hook environment with the parent's stdin attached to a
  # non-EOF source. File-based IPC sidesteps the deadlock entirely.
  local TMPIN
  TMPIN=$(mktemp -t cos_precommit.XXXXXX)
  python3 "$HELPER" "$ABS_PATH" "$FILE" >"$TMPIN" 2>/dev/null || { rm -f "$TMPIN"; return 0; }
  [[ ! -s "$TMPIN" ]] && { rm -f "$TMPIN"; return 0; }
  local OUT
  local CODE=0
  OUT=$(bash "${HOOKS_DIR}/${HOOK_SCRIPT}" <"$TMPIN" 2>&1) || CODE=$?
  rm -f "$TMPIN"
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
