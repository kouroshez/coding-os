#!/usr/bin/env bash
# warn-diff-size.sh
# PreToolUse Bash — nudge toward diff-minimal commits: when a `git commit` is
# about to run, warn (never block) if the staged diff exceeds a line threshold.
# Fail-open: any uncertainty exits 0. Spec: docs/tasks/
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

MODE="${COS_DIFF_SIZE_WARN:-1}"
if [[ "$MODE" == "off" || "$MODE" == "0" ]]; then
  cos_log_hook warn-diff-size disabled || true
  exit 0
fi

INPUT="$(cos_read_stdin_bounded 2 2>/dev/null || true)"
[[ -z "$INPUT" ]] && exit 0

CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")
[[ -z "$CMD" ]] && exit 0

# Only react to a real `git commit` (allow a leading path / env / cd prefix).
echo "$CMD" | grep -qE '(^|[;&|[:space:]])git([[:space:]]+-[^[:space:]]+)*[[:space:]]+commit([[:space:]]|$)' || exit 0
# --amend rewrites an existing commit; its size is not new churn to nudge.
echo "$CMD" | grep -qE 'commit[^|;&]*--amend' && exit 0

THRESHOLD="${COS_DIFF_SIZE_THRESHOLD:-400}"
# Measure the churn the commit will actually produce. The trunk convention is
# `git commit <path>` (working-tree paths, never `git add`-ed), so an empty
# staged diff falls back to the tracked working-tree diff vs HEAD.
STAT=$(git diff --cached --numstat 2>/dev/null || true)
[[ -z "$STAT" ]] && STAT=$(git diff --numstat HEAD 2>/dev/null || true)
[[ -z "$STAT" ]] && exit 0

TOTAL=$(echo "$STAT" | awk '{ if ($1 ~ /^[0-9]+$/) a+=$1; if ($2 ~ /^[0-9]+$/) d+=$2 } END { print a+d+0 }')
[[ "$TOTAL" =~ ^[0-9]+$ ]] || exit 0

if [ "$TOTAL" -gt "$THRESHOLD" ]; then
  echo "⚠️  diff-size: staged commit changes $TOTAL lines (> $THRESHOLD). Anti-overengineering: prefer smaller, single-purpose commits. Tune COS_DIFF_SIZE_THRESHOLD; silence with COS_DIFF_SIZE_WARN=off." >&2
  cos_log_hook warn-diff-size "large:$TOTAL" || true
fi
exit 0
