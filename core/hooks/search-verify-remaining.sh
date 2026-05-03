#!/usr/bin/env bash
# search-verify-remaining.sh — PostToolUse Bash (Phase O)
#
# PURPOSE
#   After a bulk replace (sed -i, xargs sed, xargs python), reads the
#   pattern stored by search-enforce-inventory.sh and runs a bounded verify
#   grep (timeout 15s). Reports remaining match count so the agent knows
#   whether work is complete or more sites remain.
#
#   Closes the "declared done but 20 remain" gap for Bash-based operations.
#   (verify-rename-callers.sh covers Edit-based identifier renames.)
#
# NON-BLOCKING — always exits 0.
# BOUNDED — grep runs under `timeout 15` to prevent hanging on large repos.
#
# DESIGN
#   Reads session state from $COS_AGENT_DIR/.search-inventory written by
#   the companion PreToolUse hook. If no state exists, emits a reminder.
#   Session-scoped: validates SESSION_ID before trusting state.

set -euo pipefail
source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
cos_log_hook search-verify-remaining entry 2>/dev/null || true

PAYLOAD="$(cat 2>/dev/null || true)"
[[ -z "$PAYLOAD" ]] && exit 0

CMD="$(printf '%s' "$PAYLOAD" | python3 -c '
import sys, json
try:
    d = json.loads(sys.stdin.read() or "{}")
    print(d.get("tool_input", {}).get("command", ""))
except Exception:
    pass
' 2>/dev/null || true)"
[[ -z "$CMD" ]] && exit 0

# Only fire after bulk replace operations (same detector as inventory hook)
if ! printf '%s' "$CMD" | grep -qE 'sed[[:space:]]+-i|xargs[[:space:]]+-0[[:space:]]+(sed|python)'; then
    cos_log_hook search-verify-remaining skip-not-replace 2>/dev/null || true
    exit 0
fi

# Read pattern from state written by PreToolUse hook
STATE_FILE="${COS_AGENT_DIR:-.coding-os/claude}/.search-inventory"
if [[ ! -f "$STATE_FILE" ]]; then
    cat >&2 <<MSG
⚠️  Search verify — no inventory state. Pattern unknown; verify manually:
   grep -rnF "OLD_STRING" . --exclude-dir=.git --exclude-dir=node_modules
MSG
    cos_log_hook search-verify-remaining no-state 2>/dev/null || true
    exit 0
fi

# State format: SESSION_ID<TAB>PATTERN
IFS=$'\t' read -r STATE_SESSION OLD < "$STATE_FILE" 2>/dev/null || {
    cos_log_hook search-verify-remaining bad-state 2>/dev/null || true
    exit 0
}

# Validate session ownership
CURRENT_SESSION="$(cat "$COS_SESSION_FILE" 2>/dev/null || echo "")"
if [[ -n "$CURRENT_SESSION" && "$STATE_SESSION" != "$CURRENT_SESSION" ]]; then
    cos_log_hook search-verify-remaining stale-state 2>/dev/null || true
    exit 0
fi

if [[ -z "$OLD" || "${#OLD}" -lt 2 ]]; then
    cos_log_hook search-verify-remaining empty-pattern 2>/dev/null || true
    exit 0
fi

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT" || exit 0

# Single-line to avoid newline word-split issues under pipefail
EXCL="--exclude-dir=.git --exclude-dir=node_modules --exclude-dir=dist --exclude-dir=build --exclude-dir=__pycache__ --exclude-dir=.next --exclude-dir=vendor"

# || true inside pipeline prevents pipefail from triggering on grep exit 1
# (grep exits 1 = no matches — not an error, just empty result)
REMAINING="$( { timeout 15 grep -rnF "$OLD" . $EXCL 2>/dev/null || true; } | wc -l | tr -d ' ')"
FILE_LIST="$( { timeout 15 grep -rlF "$OLD" . $EXCL 2>/dev/null || true; } | head -10)"
FILE_COUNT="$( { printf '%s\n' "$FILE_LIST" | grep -c . || true; } 2>/dev/null)"
[[ -z "$FILE_COUNT" ]] && FILE_COUNT=0

cos_log_hook search-verify-remaining "pattern=${OLD} remaining=${REMAINING}" 2>/dev/null || true

if [[ "$REMAINING" == "0" ]]; then
    rm -f "$STATE_FILE" 2>/dev/null || true
    cat >&2 <<MSG
✅ Search verify — \`${OLD}\` → 0 remaining — complete.
MSG
    exit 0
fi

if [[ "$REMAINING" == "?" ]]; then
    cat >&2 <<MSG
⚠️  Search verify — \`${OLD}\` — verify timed out (large repo). Run manually:
   grep -rnF "${OLD}" . --exclude-dir=.git --exclude-dir=node_modules
MSG
    exit 0
fi

MORE_MSG=""
[[ "$FILE_COUNT" -ge 10 ]] && MORE_MSG=" (first 10 shown)"

cat >&2 <<MSG
⚠️  Search verify — \`${OLD}\` — ${REMAINING} matches remain in ${FILE_COUNT} file(s)${MORE_MSG}:
$(printf '     - %s\n' $FILE_LIST)

   Do NOT declare done. Update remaining sites then re-verify:
     grep -rnF "${OLD}" . --exclude-dir=.git --exclude-dir=node_modules
MSG

exit 0
