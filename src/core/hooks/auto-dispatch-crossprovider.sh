#!/usr/bin/env bash
# auto-dispatch-crossprovider.sh (PostToolUse) — fire the cross-provider roles.
#
# Closes the trigger gap: supervision was enabled for six days and never ran,
# because cos_dispatch_formula_run had no automatic caller. Fires on the
# in_progress -> testing transition — the first moment finished work exists to
# review — and only for roles pinned to an adapter OTHER than this session's.
# Contract: docs/engineering/agent-supervision.md § When dispatch fires by itself.
#
# Detached: a codex dispatch measured 123s; holding the tool call open that long
# would be worse than no trigger. Fail-open throughout — a dispatch that cannot
# start must never break the task move that triggered it.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

INPUT="$(cos_read_stdin_bounded 2 2>/dev/null || true)"
# Also runs after every Bash call: leave before any fork unless a move to testing is possible.
case "$INPUT" in
  *testing*) ;;
  *) exit 0 ;;
esac
command -v jq >/dev/null 2>&1 || exit 0

TOOL_NAME=$(printf '%s' "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || true)
if [ "$TOOL_NAME" = "Bash" ]; then
  COMMAND=$(printf '%s' "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || true)
  MOVE_RE='cos[[:space:]]+task-move[[:space:]]+(TASK-[A-Za-z0-9-]*[0-9])[^;&|]*--to[=[:space:]]+testing'
  [[ "$COMMAND" =~ $MOVE_RE ]] || exit 0
  TASK_ID="${BASH_REMATCH[1]}"
else
  TO_STATUS=$(printf '%s' "$INPUT" | jq -r '.tool_input.to // empty' 2>/dev/null || true)
  [ "$TO_STATUS" = "testing" ] || exit 0
  TASK_ID=$(printf '%s' "$INPUT" | jq -r '.tool_input.task_id // empty' 2>/dev/null || true)
fi
[ -n "$TASK_ID" ] || exit 0

SESSION_ID="$(cos_current_session 2>/dev/null || true)"
[ -n "$SESSION_ID" ] || exit 0

# The ADAPTER id, never a model: `fable` is a model inside the claude adapter, and
# a model here would make every role look cross-provider (the helper also guards).
SESSION_ADAPTER="${COS_AGENT:-}"
[ -n "$SESSION_ADAPTER" ] || exit 0

_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
  _dir="$(cd -P "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ "$_src" != /* ]] && _src="$_dir/$_src"
done
HELPER="$(cd -P "$(dirname "$_src")" && pwd)/_helpers/auto_dispatch.py"
[ -f "$HELPER" ] || exit 0

# Bare python3 cannot import thinking_os; resolving the interpreter is the
# difference between this trigger working and failing open forever.
COS_PY="$(cos_resolve_python 2>/dev/null || echo python3)"
[ -x "$COS_PY" ] || COS_PY=python3

# In the foreground, and before the detached run: a review the session's own
# runtime runs as a native subagent needs the agent told to start it now, and the
# start lines of the detached ones belong in the same reply.
PLAN=""
NATIVE="$(dirname "$HELPER")/native_review.py"
if [ -f "$NATIVE" ]; then
  PLAN="$("$COS_PY" "$NATIVE" plan "$TASK_ID" "$SESSION_ID" "$SESSION_ADAPTER" 2>/dev/null || true)"
fi

nohup "$COS_PY" "$HELPER" "$TASK_ID" "$SESSION_ID" "$SESSION_ADAPTER" \
  >/dev/null 2>&1 &
disown 2>/dev/null || true

[ -n "$PLAN" ] && printf '%s\n' "$PLAN"
cos_log_hook auto-dispatch-crossprovider ok "task=${TASK_ID} adapter=${SESSION_ADAPTER}" || true
exit 0
