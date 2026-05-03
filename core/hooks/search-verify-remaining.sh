#!/usr/bin/env bash
# search-verify-remaining.sh — PostToolUse Bash (Phase O)
#
# PURPOSE
#   After a bulk replace operation (sed -i, xargs sed, python replace),
#   auto-runs a verify grep using the pattern stored by the inventory hook.
#   Reports remaining match count vs ground truth so the agent knows
#   whether work is complete or more sites remain.
#
#   Closes the "declared done but 20 remain" gap for Bash-based operations.
#   (verify-rename-callers.sh closes the same gap for Edit-based renames.)
#
# NON-BLOCKING — always exits 0.
#
# DESIGN
#   Reads state from $COS_AGENT_DIR/.search-inventory written by
#   search-enforce-inventory.sh PreToolUse. If no state exists (inventory
#   hook didn't fire — pattern undetectable), emits a reminder to verify.
#   Session-scoped: validates SESSION_ID match before trusting the state.

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

# Read state from inventory hook
STATE_FILE="${COS_AGENT_DIR:-.coding-os/claude}/.search-inventory"
if [[ ! -f "$STATE_FILE" ]]; then
    cat >&2 <<MSG
⚠️  Search verify — no inventory state found.
   Run: grep -rnF "OLD_STRING" . | wc -l  before bulk replace
   Then verify: grep -rnF "OLD_STRING" . must return 0.
MSG
    cos_log_hook search-verify-remaining no-state 2>/dev/null || true
    exit 0
fi

IFS=$'\t' read -r STATE_SESSION OLD GROUND_TRUTH < "$STATE_FILE" 2>/dev/null || {
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

# Verify grep — same excludes as inventory
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$REPO_ROOT" || exit 0

EXCL="--exclude-dir=.git --exclude-dir=node_modules --exclude-dir=dist
  --exclude-dir=build --exclude-dir=__pycache__ --exclude-dir=.next
  --exclude-dir=vendor"

REMAINING="$(grep -rnF "$OLD" . $EXCL 2>/dev/null | wc -l | tr -d ' ' || echo "?")"
FILE_LIST="$(grep -rlF "$OLD" . $EXCL 2>/dev/null | head -10 || true)"
FILE_COUNT="$(printf '%s\n' "$FILE_LIST" | grep -c . || echo 0)"

cos_log_hook search-verify-remaining "pattern=${OLD} ground_truth=${GROUND_TRUTH} remaining=${REMAINING}" 2>/dev/null || true

if [[ "$REMAINING" == "0" ]]; then
    # Clear state — pattern fully replaced
    rm -f "$STATE_FILE" 2>/dev/null || true
    cat >&2 <<MSG
✅ Search verify — \`${OLD}\` → 0 remaining (was ${GROUND_TRUTH}) — complete.
MSG
    exit 0
fi

# Remaining > 0 — warn with file list
MORE_MSG=""
if [[ "$FILE_COUNT" -ge 10 ]]; then
    MORE_MSG=" (showing first 10)"
fi

cat >&2 <<MSG
⚠️  Search verify — \`${OLD}\` — ${REMAINING} matches still remain in ${FILE_COUNT} file(s)${MORE_MSG}:
$(printf '     - %s\n' $FILE_LIST)

   Ground truth was ${GROUND_TRUTH} — do NOT declare done.
   Update remaining sites then re-verify:
     grep -rnF "${OLD}" . $EXCL
MSG

exit 0
