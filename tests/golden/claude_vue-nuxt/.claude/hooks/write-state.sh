#!/usr/bin/env bash
# Write a session-scoped state file.
# Usage: write-state.sh <state-file> <value>
# Example: write-state.sh .coding-os/claude/.thinking_os-gate "COMPLICATED 4"
#
# Prepends the current session ID so hooks can verify ownership.
# Format: "<session-id> <value>"
#
# Path routing — when <state-file> resolves (by basename) to a per-panel
# file in $COS_PER_PANEL_FILES, the write is redirected to $COS_PANEL_DIR
# so two panels of the same agent don't trample each other. Files NOT in
# the allowlist (e.g. .model, .swimlane) keep the legacy $COS_AGENT_DIR
# semantics. The routing helper cos_state_path is the SSOT for this
# decision — see src/core/hooks/cos-env.sh.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

STATE_FILE_INPUT="${1:?Usage: write-state.sh <state-file> <value>}"
VALUE="${2:?Usage: write-state.sh <state-file> <value>}"

STATE_FILE="$(cos_state_path "$STATE_FILE_INPUT")"
mkdir -p "$(dirname "$STATE_FILE")" 2>/dev/null || true

SESSION_ID=""
if [[ -f "$COS_SESSION_FILE" ]]; then
  # tr strips trailing newline / CR so the prefix is exactly one whitespace-
  # separated token. Without this, the session-id contains an embedded \n
  # and the value lands on line 2, breaking head -1 readers.
  SESSION_ID=$(tr -d '\n\r' < "$COS_SESSION_FILE" 2>/dev/null || true)
fi
# Fall back to panel-id when no session-id file exists yet (panel created
# this turn, SessionStart not yet fired). Guarantees a non-empty prefix so
# the reader's session-id check has something to compare against.
if [[ -z "$SESSION_ID" ]] && [[ -n "${COS_PANEL_ID:-}" ]]; then
  SESSION_ID="$COS_PANEL_ID"
fi

# Atomic write via tmp+mv (same filesystem → rename is atomic on POSIX).
# Concurrent writers race on the final rename; whichever wins is intact
# (no partial-write corruption visible to a reader doing head -1).
_TMP="${STATE_FILE}.tmp.$$"
printf '%s %s\n' "$SESSION_ID" "$VALUE" > "$_TMP"
mv -f "$_TMP" "$STATE_FILE"
