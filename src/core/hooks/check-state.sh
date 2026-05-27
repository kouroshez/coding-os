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
  local STATE_FILE_INPUT="$1"
  local MAX_AGE="${2:-7200}"  # default 120 min

  STATE_VALID=false
  STATE_VALUE=""
  STATE_REASON=""

  # Source cos-env up front so cos_state_path is available for routing
  # AND $COS_SESSION_FILE / $COS_PANEL_DIR resolve below.
  source "$(dirname "${BASH_SOURCE[0]}")/cos-env.sh" 2>/dev/null || true

  # Panel-first routing: if the caller passed a per-panel basename or an
  # AGENT_DIR-anchored per-panel path, we look in $COS_PANEL_DIR first
  # and fall back to the legacy $COS_AGENT_DIR location for one cycle
  # so consumer projects mid-migration don't see "Session mismatch"
  # spam. The reader trusts whichever path exists.
  local STATE_FILE
  if command -v cos_state_path >/dev/null 2>&1; then
    STATE_FILE="$(cos_state_path "$STATE_FILE_INPUT")"
  else
    STATE_FILE="$STATE_FILE_INPUT"
  fi
  # NO AGENT_DIR fallback for per-panel files. Reading another panel's
  # state via the shared agent dir is cross-panel leak — the failure
  # mode TASK-035 exists to prevent. Legacy fossils from pre-TASK-035
  # writers stay invisible until the panel re-stamps its own copy via
  # write-state.sh (which now routes through $COS_PANEL_DIR).

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

  # Check session match — STRICTLY from panel session-id file. No
  # AGENT_DIR fallback (cross-panel leak protection — see TASK-035).
  # When the panel session-id file is missing, $COS_PANEL_ID is the
  # synthesised identity that write-state.sh also uses.
  local SESSION_FILE="$COS_SESSION_FILE"
  local CURRENT_SESSION=""
  if [[ -f "$SESSION_FILE" ]]; then
    CURRENT_SESSION=$(cat "$SESSION_FILE")
  elif [[ -n "${COS_PANEL_ID:-}" ]]; then
    CURRENT_SESSION="$COS_PANEL_ID"
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
