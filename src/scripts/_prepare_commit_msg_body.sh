#!/usr/bin/env bash
# cos prepare-commit-msg — stamp the active task id into the commit subject so
# cos_task_history (`git log --all --grep TASK-NNN`) links the commit to its
# task regardless of WHO commits (terminal agent, human, Hub). Fires on every
# commit; fail-OPEN — never blocks a commit, only enriches the message.
#
# Installed by: bash src/scripts/install-git-hooks.sh
set -eu

MSG_FILE="${1:-}"
SRC="${2:-}"
[ -n "$MSG_FILE" ] || exit 0
[ -f "$MSG_FILE" ] || exit 0
# Only ordinary commits — never touch merge/squash templates.
case "$SRC" in
  merge | squash) exit 0 ;;
esac

git rev-parse --show-toplevel >/dev/null 2>&1 || exit 0

# Already names a task? leave the author's message untouched.
if grep -qE 'TASK-([A-Z][A-Z0-9]*-)?[0-9]+' "$MSG_FILE" 2>/dev/null; then
  exit 0
fi

_read_marker() {
  [ -f "$1" ] || return 0
  grep -oE 'TASK-([A-Z][A-Z0-9]*-)?[0-9]+' "$1" 2>/dev/null | head -1 || true
}

# Resolve the active task: an explicit env var wins (a task-scoped caller such
# as the Hub can set it), else this panel's marker, else the agent-level marker.
TASK_ID="$(printf '%s' "${COS_ACTIVE_TASK:-}" | grep -oE 'TASK-([A-Z][A-Z0-9]*-)?[0-9]+' | head -1 || true)"
[ -n "$TASK_ID" ] || TASK_ID="$(_read_marker "${COS_PANEL_DIR:-}/.task-current")"
[ -n "$TASK_ID" ] || TASK_ID="$(_read_marker "${COS_AGENT_DIR:-}/.task-current")"
[ -n "$TASK_ID" ] || exit 0

# Append " (TASK-NNN)" to the subject (first non-comment, non-empty line) — but
# only when it keeps the title within the 100-char commit-msg contract, so this
# can never make a later commit-msg-hook rejection. No room → leave it.
awk -v tid="$TASK_ID" '
  BEGIN { done = 0 }
  /^#/ { print; next }
  (!done && NF > 0) {
    suffix = " (" tid ")"
    if (index($0, tid) == 0 && length($0) + length(suffix) <= 100) $0 = $0 suffix
    done = 1
    print; next
  }
  { print }
' "$MSG_FILE" > "${MSG_FILE}.cos" 2>/dev/null && mv "${MSG_FILE}.cos" "$MSG_FILE" || rm -f "${MSG_FILE}.cos"

exit 0
