#!/usr/bin/env bash
# Check a session-scoped state file belongs to the current session.
# Usage: source check-state.sh  (then call: check_state <file> <max-age-seconds>)
#
# Returns via globals:
#   STATE_VALID=true/false
#   STATE_VALUE="the value without session prefix"
#   STATE_REASON="why invalid" (if invalid)

# Globals are read by callers after sourcing — shellcheck cannot follow that
# control flow, so silence SC2034 at file scope.
# shellcheck disable=SC2034

check_state() {
  local STATE_FILE="$1"
  local MAX_AGE="${2:-7200}"  # default 120 min

  STATE_VALID=false
  STATE_VALUE=""
  STATE_REASON=""

  # Check existence
  if [[ ! -f "$STATE_FILE" ]]; then
    STATE_REASON="File does not exist"
    return
  fi

  # Read session ID and value
  local CONTENT
  CONTENT=$(head -1 "$STATE_FILE")
  local FILE_SESSION
  FILE_SESSION=$(echo "$CONTENT" | awk '{print $1}')
  STATE_VALUE=$(echo "$CONTENT" | cut -d' ' -f2-)

  # Check session match — agent-agnostic via COS_STATE_DIR
  source "$(dirname "${BASH_SOURCE[0]}")/cos-env.sh" 2>/dev/null || true
  local SESSION_FILE="$COS_SESSION_FILE"
  local CURRENT_SESSION=""
  if [[ -f "$SESSION_FILE" ]]; then
    CURRENT_SESSION=$(cat "$SESSION_FILE")
  fi

  if [[ -n "$CURRENT_SESSION" ]] && [[ -n "$FILE_SESSION" ]] && [[ "$FILE_SESSION" != "$CURRENT_SESSION" ]]; then
    STATE_REASON="Session mismatch (file=$FILE_SESSION, current=$CURRENT_SESSION)"
    return
  fi

  # Check freshness
  local FILE_AGE
  if [[ "$(uname)" == "Darwin" ]]; then
    FILE_AGE=$(( $(date +%s) - $(stat -f %m "$STATE_FILE") ))
  else
    FILE_AGE=$(( $(date +%s) - $(stat -c %Y "$STATE_FILE") ))
  fi

  if [[ "$FILE_AGE" -gt "$MAX_AGE" ]]; then
    STATE_REASON="Stale ($(( FILE_AGE / 60 ))min old, max $(( MAX_AGE / 60 ))min)"
    return
  fi

  STATE_VALID=true
}
