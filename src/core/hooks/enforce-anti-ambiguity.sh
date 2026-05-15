#!/usr/bin/env bash
# PreToolUse Write|Edit hook (Phase M): Anti-Ambiguity gate.
#
# Blocks code writes when the cognitive phase is EXECUTE and the
# ambiguity cache marks failures from cos_ambiguity_check.
#
# Flow:
#   1. cos_ambiguity_check writes $COS_AGENT_DIR/.ambiguity-cache with
#      either "PASS" or "FAIL:<criteria-list>" at PLAN→EXECUTE transition.
#   2. This hook reads the cache and blocks if it contains FAIL.
#   3. CLEAR 1 tasks bypass the gate (trivial fix, no planning needed).
#
# Bypass: CLEAR 1 gate or missing cache file → allowed.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook "enforce-anti-ambiguity" "entry"

INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
[[ -z "$FILE_PATH" ]] && exit 0

# Only enforce on code files
case "$FILE_PATH" in
  *.py|*.ts|*.tsx|*.js|*.jsx|*.go|*.rs|*.sh) ;;
  *) exit 0 ;;
esac

GATE_FILE="$COS_AGENT_DIR/.thinking_os-gate"
AMBIGUITY_CACHE="$COS_AGENT_DIR/.ambiguity-cache"

# CLEAR 1 → bypass
if [[ -f "$GATE_FILE" ]]; then
  GATE_CONTENT=$(cat "$GATE_FILE" 2>/dev/null || echo "")
  if [[ "$GATE_CONTENT" == CLEAR* ]]; then
    cos_log_hook "enforce-anti-ambiguity" "allowed" "CLEAR gate bypass"
    exit 0
  fi
fi

# No cache yet → not at EXECUTE phase yet → allow
[[ ! -f "$AMBIGUITY_CACHE" ]] && exit 0

CACHE=$(cat "$AMBIGUITY_CACHE" 2>/dev/null || echo "")
if [[ "$CACHE" == FAIL:* ]]; then
  CRITERIA="${CACHE#FAIL:}"
  cos_log_hook "enforce-anti-ambiguity" "BLOCKED" "$CRITERIA"
  echo "BLOCKED: Anti-Ambiguity gate failed." >&2
  echo "  Failing criteria: $CRITERIA" >&2
  echo "" >&2
  echo "  Repair: re-dispatch the relevant formula and re-run cos_ambiguity_check." >&2
  echo "  The supervisor will return backtrack instructions automatically." >&2
  exit 1
fi

cos_log_hook "enforce-anti-ambiguity" "allowed" "gate passed"
exit 0
