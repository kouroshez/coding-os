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
  # Legacy fallback: if panel-routed path is empty but the caller's
  # original (or AGENT_DIR-equivalent) location exists, prefer that. Covers
  # (a) bare basename → agent-dir fossil from pre-migration writers, and
  # (b) callers that pre-built "$COS_AGENT_DIR/<name>" before cos_state_path
  # existed and whose target panel hasn't written its own copy yet.
  if [[ ! -f "$STATE_FILE" ]]; then
    local _base
    _base="$(basename "$STATE_FILE_INPUT")"
    case " ${COS_PER_PANEL_FILES:-} " in
      *" $_base "*)
        if [[ -f "${COS_AGENT_DIR}/${_base}" ]]; then
          STATE_FILE="${COS_AGENT_DIR}/${_base}"
        fi
        ;;
    esac
  fi

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

  # Check session match — read panel-private session-id, then legacy flat
  # $COS_AGENT_DIR/session-id during the migration window.
  local SESSION_FILE="$COS_SESSION_FILE"
  local CURRENT_SESSION=""
  if [[ -f "$SESSION_FILE" ]]; then
    CURRENT_SESSION=$(cat "$SESSION_FILE")
  elif [[ -f "${COS_AGENT_DIR}/session-id" ]]; then
    CURRENT_SESSION=$(cat "${COS_AGENT_DIR}/session-id")
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
