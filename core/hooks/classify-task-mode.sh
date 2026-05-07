#!/usr/bin/env bash
# UserPromptSubmit hook — classify the prompt into a persona-aware
# task-mode + write the result to $COS_AGENT_DIR/.task-mode.
#
# Downstream enforcement hooks read the marker so a Q&A turn doesn't
# pay the same enforcement cost as a multi-file refactor. Decision
# matrix lives in docs/engineering/task-mode-matrix.md (G/W/T mapped).
#
# Modes (priority order — first match wins):
#   formal         — .task-current already names a TASK-NNN this session
#   gov-required   — prompt verbs target governance/rules but no TASK
#   propose-formal — implementation verbs (implement/fix/refactor/...)
#   query          — Q&A verbs (what/why/explain/analyze/look/list/...)
#   adhoc          — exploratory verbs (explore/check/investigate/...)
#   chore          — short prompt, no implementation/Q&A signal
#
# `system` mode is reserved for hook-internal Bash; never written here.
# `promote` mode is set by enforce-task-start when the user accepts the
# nudge; not written here either.
#
# Bilingual (English + Persian). Always exit 0.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2)"
PROMPT=$(echo "$INPUT" | jq -r '.prompt // empty' 2>/dev/null || echo "")

# Empty prompt → leave previous mode in place (turn is a continuation).
if [[ -z "$PROMPT" ]]; then
  exit 0
fi

PL=$(printf '%s' "$PROMPT" | tr '[:upper:]' '[:lower:]')
LEN=${#PROMPT}

mkdir -p "$COS_AGENT_DIR" 2>/dev/null || true
MODE_FILE="${COS_AGENT_DIR}/.task-mode"

# 1. formal — caller already attached a TASK-NNN to this session.
TASK_FILE="${COS_AGENT_DIR}/.task-current"
if [[ -f "$TASK_FILE" ]]; then
  TASK_VAL=$(tr -d '\n\r' < "$TASK_FILE" 2>/dev/null | head -c 256)
  if [[ "$TASK_VAL" == *"TASK-"* ]]; then
    printf 'formal\n' > "$MODE_FILE"
    cos_log_hook classify-task-mode set "mode=formal len=${LEN}"
    exit 0
  fi
fi

# 2. gov-required — touches governance/rules without a task. Best-effort
#    signal; final block lives in block-protected-files.sh.
GOV_RE='(governance|critical-rules|core/rules/|adapters/.*adapter\.yaml|registry\.yaml|agents\.md|stack\.yaml)'
if printf '%s' "$PL" | command grep -qiE "$GOV_RE"; then
  printf 'gov-required\n' > "$MODE_FILE"
  cos_log_hook classify-task-mode set "mode=gov-required len=${LEN}"
  exit 0
fi

# Verb sets — order matters when the prompt mixes signals (rare but real).
IMPL_RE='(implement|build|fix|add|ship|refactor|migrate|optimi[sz]e|deploy|hotfix|بساز|پیاده ساز|ریفکتور|اصلاح|انجام بده|راه انداز)'
QUERY_RE='(what is|what does|why|explain|analy[sz]e|look at|review|show|list|describe|بررسی|توضیح|چیست|چرا|نمایش)'
EXPLORE_RE='(explore|investigate|trace|map |audit|deep dive|بررسی عمقی|ممیز|نقشه|عمیق)'

if printf '%s' "$PL" | command grep -qiE "$IMPL_RE"; then
  printf 'propose-formal\n' > "$MODE_FILE"
  cos_log_hook classify-task-mode set "mode=propose-formal len=${LEN}"
  exit 0
fi

if printf '%s' "$PL" | command grep -qiE "$QUERY_RE"; then
  printf 'query\n' > "$MODE_FILE"
  cos_log_hook classify-task-mode set "mode=query len=${LEN}"
  exit 0
fi

if printf '%s' "$PL" | command grep -qiE "$EXPLORE_RE"; then
  printf 'adhoc\n' > "$MODE_FILE"
  cos_log_hook classify-task-mode set "mode=adhoc len=${LEN}"
  exit 0
fi

# 6. chore — short prompt, no recognisable signal verbs.
if (( LEN < 80 )); then
  printf 'chore\n' > "$MODE_FILE"
  cos_log_hook classify-task-mode set "mode=chore len=${LEN}"
  exit 0
fi

# Default for long prompt without signal verbs: treat as adhoc rather than
# propose-formal — refuse to escalate enforcement on ambiguous wording.
printf 'adhoc\n' > "$MODE_FILE"
cos_log_hook classify-task-mode set "mode=adhoc-default len=${LEN}"
exit 0
