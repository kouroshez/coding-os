#!/usr/bin/env bash
# PreToolUse Write|Edit hook: Anti-Ambiguity gate.
#
# Blocks code writes when the cognitive phase is EXECUTE and the
# ambiguity cache marks failures from cos_ambiguity_check.
#
# Flow:
#   1. cos_ambiguity_check records the current check's violations into the
#      ambiguity_violations table (clearing the session's prior rows first, so a
#      passing check leaves none).
#   2. This hook queries that table for the current session and blocks (exit 2)
#      when unresolved violations exist.
#   3. CLEAR 1 tasks bypass the gate (trivial fix, no planning needed).
#
# Bypass: CLEAR 1 gate, no violations, or unresolvable tools/DB/session → allowed.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook "enforce-anti-ambiguity" "entry"

INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(printf '%s' "$INPUT" | cos_json_field tool_name)
if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
  exit 0
fi

FILE_PATH=$(printf '%s' "$INPUT" | cos_json_field tool_input.file_path)
[[ -z "$FILE_PATH" ]] && exit 0

# Only enforce on code files
case "$FILE_PATH" in
  *.py|*.ts|*.tsx|*.js|*.jsx|*.go|*.rs|*.sh) ;;
  *) exit 0 ;;
esac

GATE_FILE="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.thinking_os-gate"

# CLEAR 1 → bypass (trivial fix, no planning needed)
if [[ -f "$GATE_FILE" ]]; then
  GATE_CONTENT=$(cat "$GATE_FILE" 2>/dev/null || echo "")
  if [[ "$GATE_CONTENT" == CLEAR* ]]; then
    cos_log_hook "enforce-anti-ambiguity" "allowed" "CLEAR gate bypass"
    exit 0
  fi
fi

# Read the CURRENT ambiguity state from the canonical DB table. Fail-open when
# the tools / DB / session-id aren't resolvable (never block on infra absence).
command -v sqlite3 >/dev/null 2>&1 || exit 0
[[ -f "${COS_DB_PATH:-}" ]] || exit 0
SESSION_ID=$(cos_current_session 2>/dev/null || true)
[[ -z "$SESSION_ID" ]] && exit 0
SID_ESC=${SESSION_ID//\'/\'\'}

COUNT=$(sqlite3 "$COS_DB_PATH" \
  "SELECT COUNT(*) FROM ambiguity_violations WHERE session_id='${SID_ESC}' AND datetime(ts) > datetime('now','-120 minutes');" \
  2>/dev/null || echo 0)
[[ "$COUNT" =~ ^[0-9]+$ ]] || COUNT=0

if [[ "$COUNT" -gt 0 ]]; then
  CRITERIA=$(sqlite3 "$COS_DB_PATH" \
    "SELECT group_concat(criterion, ', ') FROM ambiguity_violations WHERE session_id='${SID_ESC}' AND datetime(ts) > datetime('now','-120 minutes');" \
    2>/dev/null || echo "")
  cos_log_hook "enforce-anti-ambiguity" "BLOCKED" "$CRITERIA"
  echo "BLOCKED: Anti-Ambiguity gate failed ($COUNT unresolved criteria)." >&2
  echo "  Failing criteria: $CRITERIA" >&2
  echo "  Repair: resolve the ambiguity, then re-run cos_ambiguity_check — a pass clears the gate." >&2
  exit 2
fi

cos_log_hook "enforce-anti-ambiguity" "allowed" "gate passed"
exit 0
