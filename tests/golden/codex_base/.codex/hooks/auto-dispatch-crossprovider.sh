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
[ -n "$INPUT" ] || exit 0
command -v jq >/dev/null 2>&1 || exit 0

TO_STATUS=$(printf '%s' "$INPUT" | jq -r '.tool_input.to // empty' 2>/dev/null || true)
[ "$TO_STATUS" = "testing" ] || exit 0

TASK_ID=$(printf '%s' "$INPUT" | jq -r '.tool_input.task_id // empty' 2>/dev/null || true)
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

nohup "$COS_PY" "$HELPER" "$TASK_ID" "$SESSION_ID" "$SESSION_ADAPTER" \
  >/dev/null 2>&1 &
disown 2>/dev/null || true

cos_log_hook auto-dispatch-crossprovider ok "task=${TASK_ID} adapter=${SESSION_ADAPTER}" || true
exit 0
