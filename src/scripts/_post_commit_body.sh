#!/usr/bin/env bash
# cos post-commit — append a Work Log line to the task shipped in this commit.
# Installed by: bash src/scripts/install-git-hooks.sh
#
# The task is detected from the committed docs/tasks/TASK-NNN-*.md file — robust,
# no panel/session resolution needed. Logs the committed CODE files + short sha.
# Idempotent per sha; fail-OPEN (the commit already landed — never error out).
set -eu

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
[ -n "$REPO_ROOT" ] || exit 0

SHA="$(git rev-parse --short HEAD 2>/dev/null || true)"
[ -n "$SHA" ] || exit 0

FILES="$(git show --name-only --format= HEAD 2>/dev/null || true)"
[ -n "$FILES" ] || exit 0

# The task this commit belongs to = the committed task file (first one wins).
TASK_FILE="$(printf '%s\n' "$FILES" | grep -oE 'docs/tasks/TASK-([A-Z][A-Z0-9]*-)?[0-9]+-[^/]*\.md' | head -1 || true)"
[ -n "$TASK_FILE" ] || exit 0
TASK_ID="$(printf '%s' "$TASK_FILE" | grep -oE 'TASK-([A-Z][A-Z0-9]*-)?[0-9]+' | head -1 || true)"
[ -n "$TASK_ID" ] || exit 0

# Code files = committed files that are NOT task markdown. No code → nothing to
# log (also breaks the self-referential loop when only the work-log line lands).
CODE_FILES="$(printf '%s\n' "$FILES" | sed '/^$/d' | grep -vE 'docs/tasks/TASK-([A-Z][A-Z0-9]*-)?[0-9]+-[^/]*\.md' || true)"
[ -n "$CODE_FILES" ] || exit 0

# Idempotent: skip if this sha is already recorded in the task body.
if grep -q "committed ${SHA}" "${REPO_ROOT}/${TASK_FILE}" 2>/dev/null; then
  exit 0
fi

# Log the sha + file COUNT, not the file list: the list is fully recoverable
# via `git show --name-only <sha>`, so enumerating it only produced a long,
# git-redundant string that the 120-char Work Log cap then truncated mid-path.
COUNT="$(printf '%s\n' "$CODE_FILES" | wc -l | tr -d ' ')"
if [ "$COUNT" -eq 1 ]; then
  SUMMARY="committed ${SHA} · ${COUNT} file"
else
  SUMMARY="committed ${SHA} · ${COUNT} files"
fi

HELPER="${COS_WORKLOG_HELPER:-${REPO_ROOT}/src/core/hooks/_helpers/work_log_append.py}"
[ -f "$HELPER" ] || exit 0
COS_PROJECT_ROOT="$REPO_ROOT" python3 "$HELPER" "$TASK_ID" "$SUMMARY" >/dev/null 2>&1 || true

exit 0
