#!/usr/bin/env bash
# PostToolUse Bash hook: after `make task-done`, remind to close the
# learning loop with cos_learn_validate.
#
# thinking-os learning pipeline:
#   Orient  → cos_learn_suggest  → patterns presented to the agent
#   Plan    → agent uses (or ignores) the patterns
#   Verify  → `make task-done`
#   After   → agent MUST call cos_learn_validate(pattern_id, was_helpful)
#             for each pattern used, so confidence formulas (LTP / LTD)
#             update. Without validation, learning stalls.
#
# This hook never blocks — it fires only on `make task-done` commands
# and prints a concise reminder if any cos_learn_suggest hit came back
# during Orient (tracked via $COS_AGENT_DIR/.learn-suggestions).
#
# Missing state file → no suggestions retrieved → nothing to validate → silent.
set -euo pipefail

INPUT=$(cat)
COS_HOOK_RUNTIME_MODEL="$(printf '%s' "$INPUT" | jq -r '.model // empty' 2>/dev/null || true)"
export COS_HOOK_RUNTIME_MODEL
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
if [[ "$TOOL" != "Bash" ]]; then
  exit 0
fi

CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
[[ -z "$CMD" ]] && exit 0

# Fire on every completion pathway: `make task-done`, `cos task-done`,
# or `cos task-move ... --to complete` (the modern CLI route that
# bypassed the old Make target). All three eventually land in
# board_os.cos_task_move with to='complete'.
if ! echo "$CMD" | grep -qE '(make|cos)[[:space:]]+task-done|cos[[:space:]]+task-move[^|;]*(--to[=[:space:]]+complete)'; then
  exit 0
fi

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
COS_STATE_DIR="${COS_STATE_DIR:-.coding-os}"
cos_log_hook remind-learn-validate fire "tool=Bash task_done=true"

SUGGESTIONS="${COS_AGENT_DIR}/.learn-suggestions"
if [[ ! -f "$SUGGESTIONS" ]] || [[ ! -s "$SUGGESTIONS" ]]; then
  # No patterns were retrieved this task → nothing to validate.
  cos_log_hook remind-learn-validate ok "suggestions=0"
  exit 0
fi

# Count the pattern IDs the agent saw (one per line, format: "id<TAB>text").
PATTERN_COUNT=$(wc -l < "$SUGGESTIONS" | tr -d ' ')
cos_log_hook remind-learn-validate reminded "suggestions=${PATTERN_COUNT}"

echo ""
echo "💡 [learn] Task done — close the learning loop."
echo "   Orient surfaced $PATTERN_COUNT learned pattern(s) this task."
echo "   For each pattern you applied (or explicitly ignored), call:"
echo "       cos_learn_validate(pattern_id=<id>, was_helpful=True|False)"
echo ""
echo "   Patterns from this task:"
head -n 5 "$SUGGESTIONS" | sed 's/^/     • /'
if [[ "$PATTERN_COUNT" -gt 5 ]]; then
  echo "     ... and $((PATTERN_COUNT - 5)) more (see $SUGGESTIONS)"
fi
echo ""
echo "   Skip this step and pattern confidence freezes — future tasks"
echo "   get the same suggestions whether they were useful or not."

# Clear the suggestions file — task is over, next task starts fresh.
: > "$SUGGESTIONS"

exit 0
