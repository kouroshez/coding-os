#!/usr/bin/env bash
# PreToolUse Edit|Write — count-grounding nudge for exhaustive intent.
#
# When intent.exhaustive=true and the agent is about to edit a code
# file under src/, warn once per session that grep-before / grep-after
# discipline is required: report `grep -rn '<pattern>' src/ | wc -l`
# BEFORE the fix and after, with the after count required to be 0.
#
# Default: WARN only (exit 0 with stderr message + per-session marker
# debounce so the warning never repeats).
#
# Strict mode (COS_ENFORCE_COUNT_GROUNDING=strict): BLOCK the edit if
# no `grep` Bash call appears in the current session's turn activity
# log. Opt-in only — strict mode without baseline tuning would flag
# many legitimate edits.
#
# Skip conditions (always exit 0):
#   - .intent.json missing or exhaustive=false
#   - file_path outside the project src/ tree
#   - file_path is an audit artifact, intent.json, or state file
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_require_or_skip jq enforce-count-grounding

INPUT="$(cos_read_stdin_bounded 2)"
if [[ -z "$INPUT" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

# Self-edit allow-list (same as enforce-audit-artifact for consistency).
case "$FILE_PATH" in
  */docs/tasks/audits/*|docs/tasks/audits/*) exit 0 ;;
  */docs/_meta/*|docs/_meta/*) exit 0 ;;
  */.coding-os/*|.coding-os/*) exit 0 ;;
  /tmp/*|*/tmp/*) exit 0 ;;
esac

# Only nudge for edits inside src/ — out-of-src edits (docs, config,
# tests) don't need the same residual-count contract.
case "$FILE_PATH" in
  */src/*|src/*) ;;
  *) exit 0 ;;
esac

INTENT_FILE="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.intent.json"  # panel-first
[[ -f "$INTENT_FILE" ]] || INTENT_FILE="${COS_AGENT_DIR}/.intent.json"
if [[ ! -f "$INTENT_FILE" ]]; then
  exit 0
fi
EXHAUSTIVE=$(jq -r '.exhaustive // false' "$INTENT_FILE" 2>/dev/null || echo "false")
if [[ "$EXHAUSTIVE" != "true" ]]; then
  exit 0
fi

# Per-session debounce — warn once per session.
MARKER="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.count-grounding-nudged"  # panel-first
if [[ -f "$MARKER" ]]; then
  exit 0
fi

# Detect grep activity in this session via turn-activity log.
ACTIVITY_LOG="${COS_AGENT_DIR}/.turn-activity.log"
HAS_GREP=0
if [[ -f "$ACTIVITY_LOG" ]] && grep -q "grep" "$ACTIVITY_LOG" 2>/dev/null; then
  HAS_GREP=1
fi
if [[ "$HAS_GREP" -eq 0 ]] && [[ -f "$COS_HOOK_LOG" ]] && grep -q "grep.*wc -l" "$COS_HOOK_LOG" 2>/dev/null; then
  HAS_GREP=1
fi

if [[ "$HAS_GREP" -eq 1 ]]; then
  # Grounding already in this session — silent pass, mark debounced.
  touch "$MARKER" 2>/dev/null || true
  exit 0
fi

PATTERNS=$(jq -r '.matched_exhaustive | join(", ")' "$INTENT_FILE" 2>/dev/null || echo "")

cos_log_hook enforce-count-grounding nudge "file=${FILE_PATH} patterns=[${PATTERNS}]"
touch "$MARKER" 2>/dev/null || true

MSG="count-grounding reminder (exhaustive intent: [${PATTERNS}]):
  Before fixing ${FILE_PATH}, run a grep-count baseline:
    grep -rn '<pattern>' src/ tests/ docs/ | wc -l
  Then iterate fix → re-grep until the count reaches 0.  Record both
  numbers in docs/tasks/audits/audit-<slug>.md (Hits before / Hits
  after columns).  The completion guardian enforces counts_after=0
  per category before allowing the 'done' claim.

  This is a soft warning (once per session).  To enforce as a hard
  block, export COS_ENFORCE_COUNT_GROUNDING=strict."

if [[ "${COS_ENFORCE_COUNT_GROUNDING:-warn}" == "strict" ]]; then
  echo "BLOCKED: ${MSG}" >&2
  exit 2
fi

echo "warning: ${MSG}" >&2
exit 0
