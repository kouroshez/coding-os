#!/usr/bin/env bash
# UserPromptSubmit hook — heuristic Complexity Gate nudge + Rule 18 task reconciliation.
#
# Reads user prompt from stdin payload. Counts signal words to classify
# as CLEAR / COMPLICATED / COMPLEX / CHAOTIC. For COMPLICATED+ emits an
# additional-context block mandating Rule 18 task board check (cos_task_board),
# Complexity Gate recording, and thinking_os skill load.
# Debounced per session via marker file so the same session is nudged at most once.
#
# Always exits 0 — never blocks input.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"
PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty' 2>/dev/null || echo "")

# Skip empty / very short prompts (almost certainly CLEAR).
LEN=${#PROMPT}
if [[ "$LEN" -lt 80 ]]; then
  exit 0
fi

# Debounce: one nudge per session. Marker cleared by session-context.sh on startup.
MARKER="${COS_AGENT_DIR}/.zoom-prompt-suggested"
if [[ -f "$MARKER" ]]; then
  exit 0
fi

# Existing gate already recorded? No nudge needed.
GATE_FILE="${COS_AGENT_DIR}/.thinking_os-gate"
if [[ -f "$GATE_FILE" ]]; then
  exit 0
fi

# Lowercase prompt for matching.
PL=$(printf '%s' "$PROMPT" | tr '[:upper:]' '[:lower:]')

# Signal words. Persian + English mixed (this repo is bilingual).
COMPLICATED_RE='design|architect|plan|debug|investigate|refactor|multiple|all of|comprehensive|deep|enterprise|trace|map |dependency|persona|scenario|طراحی|معماری|پلن|دیباگ|ریفکتور|عمیق|سازمان|چندین|همه |تحلیل|نقشه|پرسنا'
COMPLEX_RE='best way|optimal|optimize|strategy|unknown|research|what if|trade.?off|بهترین راه|بهینه|استراتژی|نامعلوم'
CHAOTIC_RE='down|broken|crash|outage|urgent|emergency|asap|hotfix|p0|خراب|بحران|فوری|اضطرار'

count_re() {
  # grep -o returns 1 on no match — swallow it so pipefail does not abort
  # the whole hook just because zero signals matched.
  local n
  n=$(printf '%s' "$1" | { grep -oE "$2" 2>/dev/null || true; } | wc -l | tr -d ' ')
  printf '%s' "${n:-0}"
}

CHAOS=$(count_re "$PL" "$CHAOTIC_RE")
COMPLEX=$(count_re "$PL" "$COMPLEX_RE")
COMPLICATED=$(count_re "$PL" "$COMPLICATED_RE")

CLASSIFICATION=""
DIM_HINT=""
if [[ "$CHAOS" -ge 1 ]]; then
  CLASSIFICATION="CHAOTIC"
  DIM_HINT="1+"
elif [[ "$COMPLEX" -ge 1 ]]; then
  CLASSIFICATION="COMPLEX"
  DIM_HINT="$((COMPLEX + COMPLICATED))"
elif [[ "$COMPLICATED" -ge 2 ]] || [[ "$LEN" -gt 600 ]]; then
  CLASSIFICATION="COMPLICATED"
  DIM_HINT="$COMPLICATED"
fi

if [[ -z "$CLASSIFICATION" ]]; then
  exit 0
fi

cos_log_hook nudge-thinking-os fire "class=${CLASSIFICATION} len=${LEN} cplx=${COMPLICATED} cplex=${COMPLEX} chaos=${CHAOS}"

# Set marker so we nudge at most once per session.
mkdir -p "$(dirname "$MARKER")" 2>/dev/null || true
printf '%s' "$CLASSIFICATION" > "$MARKER" 2>/dev/null || true

# Emit structured hookSpecificOutput JSON — Claude Code renders UserPromptSubmit
# hooks that return this format as a compact labeled "additionalContext" block,
# matching the pattern used by caveman-mode-tracker.js for consistent UI.
CONTEXT="[thinking_os ${CLASSIFICATION} ~${DIM_HINT}dim] MANDATORY: (1) cos_task_board [Rule 18] (2) write-state.sh gate (3) Skill(thinking_os) (4) cos_compose_chain — heuristic, re-classify after full read."
printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":$(printf '%s' "$CONTEXT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}"

exit 0
