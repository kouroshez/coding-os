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
  # tr strips trailing newline / CR so the prefix is exactly one whitespace-
  # separated token. Without this, the session-id contains an embedded \n
  # and the value lands on line 2, breaking head -1 readers.
  SESSION_ID=$(tr -d '\n\r' < "$COS_SESSION_FILE" 2>/dev/null || true)
fi

# Atomic write via tmp+mv (same filesystem → rename is atomic on POSIX).
# Concurrent writers race on the final rename; whichever wins is intact
# (no partial-write corruption visible to a reader doing head -1).
_TMP="${STATE_FILE}.tmp.$$"
printf '%s %s\n' "$SESSION_ID" "$VALUE" > "$_TMP"
mv -f "$_TMP" "$STATE_FILE"
