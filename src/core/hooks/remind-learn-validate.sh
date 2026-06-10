#!/usr/bin/env bash
# PostToolUse Bash hook: after `cos task-done`, remind to close the
# learning loop with cos_learn_validate.
#
# thinking_os learning pipeline:
#   Orient  → cos_learn_suggest  → patterns presented to the agent
#   Plan    → agent uses (or ignores) the patterns
#   Verify  → `cos task-done`
#   After   → agent MUST call cos_learn_validate(pattern_id, was_helpful)
#             for each pattern used, so confidence formulas (LTP / LTD)
#             update. Without validation, learning stalls.
#
# This hook never blocks — it fires only on task-done commands
# and prints a concise reminder if any cos_learn_suggest hit came back
# during Orient (tracked via $COS_AGENT_DIR/.learn-suggestions).
#
# Missing state file → no suggestions retrieved → nothing to validate → silent.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"

# Fast-path: this reminder only fires on task-completion (task-done / task-move
# --to complete). If the raw payload mentions neither there is nothing to do —
# bail before any jq spawn (fires on EVERY Bash tool call).
case "$INPUT" in
  *task-done*|*task-move*) ;;
  *) exit 0 ;;
esac

COS_HOOK_RUNTIME_MODEL="$(printf '%s' "$INPUT" | jq -r '.model // empty' 2>/dev/null || true)"
export COS_HOOK_RUNTIME_MODEL
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
if [[ "$TOOL" != "Bash" ]]; then
  exit 0
fi

CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")
[[ -z "$CMD" ]] && exit 0

# Fire on every completion pathway: `make task-done`, `cos task-done`,
# or `cos task-move ... --to complete` (the modern CLI route that
# bypassed the old Make target). All three eventually land in
# board_os.cos_task_move with to='complete'.
if ! echo "$CMD" | grep -qE '(make|cos)[[:space:]]+task-done|cos[[:space:]]+task-move[^|;]*(--to[=[:space:]]+complete)'; then
  exit 0
fi

COS_STATE_DIR="${COS_STATE_DIR:-.coding-os}"
cos_log_hook remind-learn-validate fire "tool=Bash task_done=true"

# Panel-first: auto_compose writes .learn-suggestions to the
# panel dir and session-context resets it there, so read panel-first with an
# agent-level fallback for legacy writers.
SUGGESTIONS="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.learn-suggestions"
[[ -f "$SUGGESTIONS" ]] || SUGGESTIONS="${COS_AGENT_DIR}/.learn-suggestions"
if [[ ! -f "$SUGGESTIONS" ]] || [[ ! -s "$SUGGESTIONS" ]]; then
  # No patterns were retrieved this task → nothing to validate.
  cos_log_hook remind-learn-validate ok "suggestions=0"
  exit 0
fi

# Count the pattern IDs the agent saw (one per line, format: "id<TAB>text").
PATTERN_COUNT=$(wc -l < "$SUGGESTIONS" | tr -d ' ')
cos_log_hook remind-learn-validate reminded "suggestions=${PATTERN_COUNT}"

# Close the learning loop AUTOMATICALLY (B1): validate each surfaced lesson
# against this session's friction — recurred → not-helpful, else helpful. Reuses
# learn_validate (LTP/LTD + 1h throttle so a manual agent call still wins).
# Fire-and-forget — a failure here must never break task-done.
SID="$(cos_current_session 2>/dev/null || echo "")"
DB="${COS_DB_PATH:-${COS_STATE_DIR}/coding-os.db}"
AV_OUT="$(python3 "$(dirname "$0")/_helpers/auto_validate_lessons.py" "$SID" "$DB" "$SUGGESTIONS" 2>/dev/null || true)"

echo ""
echo "💡 [learn] Task done — learning loop closed."
if [[ -n "$AV_OUT" ]]; then
  echo "   ✓ ${AV_OUT}"
  cos_log_hook remind-learn-validate ok "auto_validate=1"
fi
echo "   Orient surfaced $PATTERN_COUNT learned pattern(s) this task; confidence"
echo "   was updated automatically. To override a specific one, call:"
echo "       cos_learn_validate(pattern_id=<id>, was_helpful=True|False)"
head -n 5 "$SUGGESTIONS" | sed 's/^/     • /'
if [[ "$PATTERN_COUNT" -gt 5 ]]; then
  echo "     ... and $((PATTERN_COUNT - 5)) more (see $SUGGESTIONS)"
fi

# Clear the suggestions file — task is over, next task starts fresh.
: > "$SUGGESTIONS"

exit 0
