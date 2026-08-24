#!/usr/bin/env bash
# Stop hook: refuse to end a turn that drafted prose without auditing it.
#
# Purpose: nudge-humanizer.sh fires on intent and says "load the skill".
# Loading is not applying. Three times in one session an agent loaded the
# skill, drafted, and shipped text still carrying the patterns the skill
# names — because nothing checked the OUTPUT. This is the output-side gate:
# prose intent was detected, so the turn cannot end until the agent has run
# the pattern list back over what it actually wrote and recorded the count.
#
# The first pass is assumed wrong. That is the whole point of the second one.
#
# Loop-safe: honours stop_hook_active, so a failed audit can never trap a
# session. Fails open on every ambiguity.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"

# Loop guard first: if the runtime is already re-entering after this hook
# blocked once, never block again. A gate that cannot be escaped is worse
# than the drift it prevents.
ALREADY=$(printf '%s' "$INPUT" | cos_json_field stop_hook_active)
if [[ "$ALREADY" == "true" ]]; then
  exit 0
fi

PANEL="${COS_PANEL_DIR:-${COS_AGENT_DIR:-}}"
[[ -n "$PANEL" ]] || exit 0

# Did this session ever draft prose? nudge-humanizer stamps one marker per
# intent class. No marker means no prose, so nothing to audit.
NUDGE_DIR="${PANEL}/.humanizer-nudge"
if [[ ! -d "$NUDGE_DIR" ]] || [[ -z "$(ls -A "$NUDGE_DIR" 2>/dev/null || true)" ]]; then
  exit 0
fi

CLASSES=$(ls -A "$NUDGE_DIR" 2>/dev/null | tr '\n' ',' | sed 's/,$//')

# The receipt. check-state.sh scopes it to the current session, so a receipt
# left by yesterday's session does not satisfy today's turn.
AUDIT_FILE="${PANEL}/.humanizer-audit"
if [[ -f "$(dirname "$0")/check-state.sh" ]]; then
  source "$(dirname "$0")/check-state.sh"
  check_state "$AUDIT_FILE" 7200
  if [[ "$STATE_VALID" == "true" ]]; then
    cos_log_hook enforce-humanizer-audit pass "classes=${CLASSES} receipt=${STATE_VALUE}" || true
    exit 0
  fi
else
  exit 0
fi

cos_log_hook enforce-humanizer-audit block "classes=${CLASSES}" || true

cat >&2 <<EOF
BLOCKED: this turn drafted prose (intent class: ${CLASSES}) and has not been audited.

WHY: loading the humanizer skill is not the same as applying it. The draft you
are about to ship is the FIRST pass, and a first pass carrying the skill's own
patterns is the normal case, not the exception.

Do this now, against src/core/skills/humanizer/references/patterns.md:

  1. Re-read every paragraph of prose you wrote this turn.
  2. Name each pattern you find, by number. Check at minimum:
     - 9  "not X, it's Y" and clipped negative tails
     - 10 forced groups of three
     - 14 em and en dashes (search for the characters; do not eyeball it)
     - 31 forced punchlines and manufactured gravity
     - 33 fake-candid openings
     - 34 answering objections nobody raised
     - 36 uniform sentence and paragraph length
     Plus: a formula you have already used in another draft this session,
     and any number or fact that no source in this session supports.
  3. Fix what you found, then record the receipt:

       bash ".${COS_AGENT}/hooks/write-state.sh" .humanizer-audit "reviewed:<count>"

Report the findings to the user in the reply. "reviewed:0" is a claim you are
making to them, not a formality.
EOF

exit 2
