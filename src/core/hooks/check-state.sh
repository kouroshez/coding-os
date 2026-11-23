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
  # mode this rule exists to prevent. Legacy fossils from earlier
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
  # AGENT_DIR fallback (cross-panel leak protection).
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

# --- Task-gate helpers (docs/engineering/task-mode-matrix.md § Task enforcement
# is not a mode decision). Each call to check_state above resets STATE_*.

# Built-in code extensions; `.coding-os.yaml` `code_extensions` adds to them, so a
# project initialised with a narrow list is still covered.
_COS_CODE_EXTENSIONS="py ts tsx js jsx mjs cjs go rs java kt kts scala rb php swift dart cs c cc cpp h hpp m mm vue svelte"

_cos_project_root() {
  printf '%s' "${COS_PROJECT_ROOT:-$(dirname "${COS_STATE_DIR:-./.coding-os}")}"
}

cos_is_code_file() {
  local path="$1" ext extra="" cfg candidate
  [[ "$path" == *.* ]] || return 1
  ext="${path##*.}"
  cfg="$(_cos_project_root)/.coding-os.yaml"
  if [[ -f "$cfg" ]]; then
    extra=$(awk '
      /^code_extensions:/ { rest = $0; sub(/^code_extensions:[ \t]*/, "", rest)
        if (rest ~ /^\[/) { gsub(/[][,]/, " ", rest); print rest; exit }
        inlist = 1; next }
      inlist && /^[ \t]*-[ \t]*/ { item = $0; sub(/^[ \t]*-[ \t]*/, "", item); printf "%s ", item; next }
      inlist { exit }' "$cfg" 2>/dev/null | tr -d "\"'")
  fi
  for candidate in $_COS_CODE_EXTENSIONS $extra; do
    [[ "$ext" == "$candidate" ]] && return 0
  done
  return 1
}

# Frontmatter `status:` of a task file; exit 1 when no file names that id.
cos_task_status() {
  local task_id="$1" root file
  for root in "$(_cos_project_root)" "${CLAUDE_PROJECT_DIR:-}" "."; do
    [[ -n "$root" ]] || continue
    for file in "$root"/docs/tasks/"$task_id"-*.md "$root"/docs/tasks/"$task_id".md; do
      [[ -f "$file" ]] || continue
      awk '/^---[ \t]*$/ { fence++; if (fence == 2) exit; next }
           fence == 1 && /^status:/ { sub(/^status:[ \t]*/, ""); gsub(/["\r]/, ""); print; exit }' "$file"
      return 0
    done
  done
  return 1
}

cos_task_mode() {
  local mode_file="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.task-mode"
  [[ -f "$mode_file" ]] || mode_file="${COS_AGENT_DIR:-}/.task-mode"
  [[ -f "$mode_file" ]] && tr -d '\n\r' < "$mode_file" 2>/dev/null | head -c 24
  return 0
}

# Sets ACTIVE_TASK_ID / ACTIVE_TASK_STATUS from this panel's marker. Returns 0
# only when that task is in_progress or emergency: a marker left behind by a
# task in testing, complete or blocked no longer unlocks edits.
cos_active_task() {
  ACTIVE_TASK_ID=""
  ACTIVE_TASK_STATUS=""
  check_state "${COS_PANEL_DIR:-$COS_AGENT_DIR}/.task-current" 28800
  [[ "${STATE_VALID:-}" == "true" ]] || return 1
  ACTIVE_TASK_ID=$(printf '%s\n' "$STATE_VALUE" | grep -oE 'TASK-([A-Z][A-Z0-9]*-)?[0-9]+' | head -1)
  [[ -n "$ACTIVE_TASK_ID" ]] || return 1
  ACTIVE_TASK_STATUS=$(cos_task_status "$ACTIVE_TASK_ID") || ACTIVE_TASK_STATUS="unknown (no task file)"
  case "$ACTIVE_TASK_STATUS" in
    in_progress|emergency) return 0 ;;
  esac
  return 1
}

# A recorded `CLEAR 1` gate excuses a trivial edit, but never in a turn whose
# prompt asked for implementation or governance work.
cos_clear1_escape() {
  check_state "${COS_PANEL_DIR:-$COS_AGENT_DIR}/.thinking_os-gate" 7200
  [[ "${STATE_VALID:-}" == "true" ]] || return 1
  [[ "$(printf '%s' "$STATE_VALUE" | awk '{print $1" "$2}')" == "CLEAR 1" ]] || return 1
  case "$(cos_task_mode)" in
    propose-formal|gov-required) return 1 ;;
  esac
  return 0
}
