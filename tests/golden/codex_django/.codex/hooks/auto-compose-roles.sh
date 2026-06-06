#!/usr/bin/env bash
# auto-compose-roles.sh (UserPromptSubmit) — auto-fire role composition.
#
# Closes the dead-trigger gap: cos_compose_chain had no automatic
# caller, so .roles was never written and the Hub Roles panel was always
# empty. This hook reads the recorded complexity gate and, for COMPLICATED/
# COMPLEX classifications, composes a role chain via _helpers/auto_compose.py
# (which stamps .roles/.role + emits a compose_done trace). It surfaces the
# composed lead role as additionalContext so the agent knows its chain.
#
# Debounce: once per session per gate value (re-composes if the gate class
# changes). Fail-open: any error exits 0 — never blocks the prompt.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook auto-compose-roles enter || true

# Read the user prompt from stdin so the composer gets real action/domain
# signals. Without it the chain collapses to ['analyst'] for every
# COMPLICATED/COMPLEX prompt. Bounded; fail-open to empty.
INPUT="$(cos_read_stdin_bounded 2 2>/dev/null || true)"
PROMPT="$(printf '%s' "$INPUT" | jq -r '.prompt // empty' 2>/dev/null || true)"

GATE_FILE="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.thinking_os-gate"
[[ -f "$GATE_FILE" ]] || exit 0

# Validate gate freshness/ownership (same contract as nudge-thinking-os).
source "$(dirname "$0")/check-state.sh" 2>/dev/null || true
if type check_state >/dev/null 2>&1; then
  check_state "$GATE_FILE" 7200
  [[ "${STATE_VALID:-}" == "true" ]] || exit 0
  GATE_VALUE="${STATE_VALUE:-}"
else
  GATE_VALUE=$(head -1 "$GATE_FILE" 2>/dev/null | cut -d' ' -f2- || true)
fi

GATE_CLASS=$(printf '%s' "$GATE_VALUE" | awk '{print $1}')
GATE_DIMS=$(printf '%s' "$GATE_VALUE" | awk '{print $2}')
case "$GATE_CLASS" in
  COMPLICATED|COMPLEX) ;;
  *) exit 0 ;;
esac

# Debounce: one compose per (session, gate-class). Marker records the class
# we last composed for; re-compose only when the class changes.
MARKER="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.roles-composed"
if [[ -f "$MARKER" ]]; then
  LAST=$(head -1 "$MARKER" 2>/dev/null | tr -d '\n\r' || true)
  [[ "$LAST" == "$GATE_CLASS" ]] && exit 0
fi

# Resolve the helper through the hook symlink.
_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
  _dir="$(cd -P "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ "$_src" != /* ]] && _src="$_dir/$_src"
done
HSRC="$(cd -P "$(dirname "$_src")" && pwd)"
HELPER="${HSRC}/_helpers/auto_compose.py"
[[ -f "$HELPER" ]] || exit 0

# Panel-first target so .roles/.role land where the banner + Hub read them
# (same per-panel scope as every other cognitive marker).
TARGET_DIR="${COS_PANEL_DIR:-${COS_AGENT_DIR:-${COS_STATE_DIR:-.coding-os}/${COS_AGENT:-claude}}}"
OUT=$(printf '%s' "$PROMPT" | python3 "$HELPER" "$GATE_CLASS" "${GATE_DIMS:-1}" "$TARGET_DIR" 2>/dev/null || true)

mkdir -p "$(dirname "$MARKER")" 2>/dev/null || true
printf '%s' "$GATE_CLASS" > "$MARKER" 2>/dev/null || true

if [[ -n "$OUT" ]]; then
  cos_log_hook auto-compose-roles ok "class=${GATE_CLASS}" || true
  printf '%s' "{\"hookSpecificOutput\":{\"hookEventName\":\"UserPromptSubmit\",\"additionalContext\":$(printf '%s' "$OUT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')}}"
else
  cos_log_hook auto-compose-roles ok "class=${GATE_CLASS} composed=none" || true
fi

exit 0
