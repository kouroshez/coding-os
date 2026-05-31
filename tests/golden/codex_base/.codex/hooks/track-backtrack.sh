#!/usr/bin/env bash
# PostToolUse hook (Phase M): Anti-Paralysis backtrack counter.
#
# Fires when cos_backtrack_log is called. Reads the session backtrack
# count from the tool's output envelope and emits a non-blocking
# advisory when the count reaches threshold.
#
# Thresholds (non-blocking, advisory only):
#   ≥3 → warn
#   ≥5 → stronger advisory
#
# This hook never blocks — it only informs. Agent autonomy is preserved.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_log_hook "track-backtrack" "entry"

INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
if [[ "$TOOL" != "mcp__coding-os__cos_backtrack_log" ]]; then
  exit 0
fi

# Parse the advisory from the tool output envelope
ADVISORY=$(echo "$INPUT" | jq -r '.tool_response.data.advisory // empty' 2>/dev/null || echo "")
COUNT=$(echo "$INPUT" | jq -r '.tool_response.data.count // 0' 2>/dev/null || echo "0")

if [[ -n "$ADVISORY" && "$ADVISORY" != "null" ]]; then
  cos_log_hook "track-backtrack" "advisory" "count=$COUNT"
  echo "[Anti-Paralysis] $ADVISORY" >&2
fi

exit 0
