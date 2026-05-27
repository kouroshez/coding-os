#!/usr/bin/env bash
# Stop hook — anti-completion-bias nudge for exhaustive-intent sessions.
#
# Complementary to verify-completion-claim.sh (G4 guardian):
#   Guardian catches KNOWN gaps (unchecked rows, missing evidence).
#   This nudge catches SILENT exclusions — categories the agent never
#   added to the audit list in the first place.
#
# Fires ONCE per session via .premature-done-nudged marker.  Only when:
#   - .intent.json shows exhaustive=true (else no obligation)
#   - At least one active audit file exists (else nothing to interrogate)
#
# Emits a one-line Claude Code additionalContext block asking the agent
# to name 3 categories it did NOT include in the audit and to justify
# the exclusion before submitting EvidenceBundle. Always exits 0.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_require_or_skip jq prevent-premature-done

INTENT_FILE="${COS_AGENT_DIR}/.intent.json"
if [[ ! -f "$INTENT_FILE" ]]; then
  exit 0
fi

EXHAUSTIVE=$(jq -r '.exhaustive // false' "$INTENT_FILE" 2>/dev/null || echo "false")
if [[ "$EXHAUSTIVE" != "true" ]]; then
  exit 0
fi

# Per-session debounce — only nudge once per session.
MARKER="${COS_AGENT_DIR}/.premature-done-nudged"
if [[ -f "$MARKER" ]]; then
  exit 0
fi

# Only nudge if at least one active audit file exists. Without one,
# enforce-audit-artifact already covers the situation (a "create the
# artifact first" block).
AUDIT_DIR="docs/tasks/audits"
ACTIVE_COUNT=0
if [[ -d "$AUDIT_DIR" ]]; then
  AUDIT_FILES=$(compgen -G "${AUDIT_DIR}/audit-*.md" 2>/dev/null || true)
  if [[ -n "$AUDIT_FILES" ]]; then
    # Match BOTH YAML (`^status: in_progress`) and markdown bold
    # (`**Status:** in_progress`) — historic audits use the latter; the
    # template mandates the former. Mirrors session-context.sh.
    ACTIVE_COUNT=$(grep -lE "(^status:[[:space:]]+in_progress|\*\*Status:\*\*[[:space:]]+in_progress)" $AUDIT_FILES 2>/dev/null | wc -l | tr -d ' ')
  fi
fi
if [[ "$ACTIVE_COUNT" -eq 0 ]]; then
  exit 0
fi

cos_log_hook prevent-premature-done fire "active_audits=${ACTIVE_COUNT}"
touch "$MARKER" 2>/dev/null || true

MATCHED=$(jq -r '.matched_exhaustive | join(", ")' "$INTENT_FILE" 2>/dev/null || echo "")

CONTEXT="[Anti-completion-bias] Before any 'done' claim: name 3 categories you did NOT add to the audit list and explain why each was excluded (out-of-scope · already-fixed-prior · n/a-for-this-repo). The exhaustive vocabulary [${MATCHED}] forbids implicit exclusion — every skipped category must be a deliberate, justified choice. If you cannot name 3, you are missing categories — add them to the audit, run the count-before grep, and continue."

printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"Stop\",\"additionalContext\":$(printf '%s' "$CONTEXT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}"

exit 0
