#!/usr/bin/env bash
# Write a session-scoped state file.
# Usage: write-state.sh <state-file> <value>
# Example: write-state.sh .coding-os/.thinking_os-gate "COMPLICATED 4"
#
# Prepends the current session ID so hooks can verify ownership.
# Format: "<session-id> <value>"
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

STATE_FILE="${1:?Usage: write-state.sh <state-file> <value>}"
VALUE="${2:?Usage: write-state.sh <state-file> <value>}"

SESSION_ID=""
if [[ -f "$COS_SESSION_FILE" ]]; then
  SESSION_ID=$(cat "$COS_SESSION_FILE")
fi

# Write: session-id on first field, rest is the value
echo "$SESSION_ID $VALUE" > "$STATE_FILE"
