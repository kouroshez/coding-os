#!/usr/bin/env bash
# Stop hook: warn if this session made code changes but captured zero
# observations. A silent capture failure (DB path broken, schema stale,
# missing RAG extras) leaves the session with "work happened, nothing
# was learned" — invisible unless we actively check.
#
# Runs at session end (Stop event). Never blocks — at this point the
# session is already wrapping up — just surfaces the drift so the next
# session starts from a clean, known state.
#
# Two signals:
#   1. $COS_STATE_DIR/.capture-errors.log exists → at least one
#      capture.py invocation failed this session. Print the error tail.
#   2. observations table in the DB has zero rows tagged with this
#      session_id, but the agent did edit code files this session. Warn
#      about the silent failure.
#
# If MCP is down (warn-mcp-down already banner'd at SessionStart), we
# still produce a concise "session-end recap" confirming the
# observations count so the human knows exactly what was / wasn't saved.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

COS_STATE_DIR="${COS_STATE_DIR:-.coding-os}"
COS_DB_PATH="${COS_DB_PATH:-$COS_STATE_DIR/coding-os.db}"
SESSION_FILE="${COS_SESSION_FILE:-$COS_STATE_DIR/session-id}"

SESSION_ID=""
if [[ -f "$SESSION_FILE" ]]; then
  SESSION_ID=$(tr -d '\n\r' < "$SESSION_FILE" | head -c 128)
fi
[[ -z "$SESSION_ID" ]] && exit 0
cos_log_hook check-capture-worked fire

ERROR_LOG="$COS_STATE_DIR/.capture-errors.log"
ERRORS_FOUND=0

# --- 1. Scan capture error log ---------------------------------------
if [[ -f "$ERROR_LOG" ]] && [[ -s "$ERROR_LOG" ]]; then
  ERRORS_FOUND=$(wc -l < "$ERROR_LOG" | tr -d ' ')
fi

# --- 2. Count observations in this session ---------------------------
OBS_COUNT=-1
if [[ -f "$COS_DB_PATH" ]]; then
  # SQLite may not be installed in bare environments, so fallback to
  # Python which we already depend on.
  # bash 5.3.9 deadlocks `$(python3 - <<HEREDOC)`. Form B (helper file)
  # is the only deadlock-immune pattern.
  _src="${BASH_SOURCE[0]}"
  while [ -L "$_src" ]; do
    _dir="$(cd -P "$(dirname "$_src")" && pwd)"
    _src="$(readlink "$_src")"
    [[ "$_src" != /* ]] && _src="$_dir/$_src"
  done
  HSRC="$(cd -P "$(dirname "$_src")" && pwd)"
  unset _src _dir
  HELPER="${HSRC}/_helpers/observation_count.py"
  if [[ -f "$HELPER" ]]; then
    OBS_COUNT=$(python3 "$HELPER" "$COS_DB_PATH" "$SESSION_ID" 2>/dev/null || echo -1)
  else
    OBS_COUNT=-1
  fi
fi

# --- 2b. Count Write/Edit operations this session ------------------
# A read-only session (no code edits) is EXPECTED to have 0 observations,
# so the "0 obs" branch below is not actionable. We only flag drift when
# the session actually attempted to capture something. Heuristic:
# capture-observation.sh logs `fire tool=<X>` for every PostToolUse it
# sees; counting `tool=Write` + `tool=Edit` entries for this session
# tells us whether capture had any work to do.
HOOKS_LOG="${COS_STATE_DIR}/.hooks.log"
WRITE_EDIT_COUNT=0
if [[ -f "$HOOKS_LOG" ]]; then
  WRITE_EDIT_COUNT=$(grep -c "session=${SESSION_ID}.*\[capture-observation\] \[fire\].*tool=\(Write\|Edit\)" "$HOOKS_LOG" 2>/dev/null || echo 0)
  WRITE_EDIT_COUNT=${WRITE_EDIT_COUNT//[^0-9]/}
  : "${WRITE_EDIT_COUNT:=0}"
fi

# --- 3. Decide what to say ------------------------------------------
# Silent success path: no errors AND observations > 0 → nothing to say.
if [[ "$ERRORS_FOUND" == "0" ]] && [[ "$OBS_COUNT" -gt 0 ]]; then
  cos_log_hook check-capture-worked ok "observations=${OBS_COUNT}"
  exit 0
fi

# Silent expected path: no errors, 0 obs, AND 0 Write/Edit calls →
# read-only / dispatch-only session. Capture had nothing to record;
# suppress the warning (it would be noise on every read-only session).
if [[ "$ERRORS_FOUND" == "0" ]] && [[ "$OBS_COUNT" -eq 0 ]] && [[ "$WRITE_EDIT_COUNT" -eq 0 ]]; then
  cos_log_hook check-capture-worked ok "observations=0 reason=read-only-session"
  exit 0
fi

# Be useful at session end. Keep output short.
# Stop hooks in current Codex expect JSON on stdout when they emit
# anything at exit 0, so warnings go to stderr instead.
echo "" >&2
echo "📊 [session recap] observations captured: $OBS_COUNT" >&2

if [[ "$ERRORS_FOUND" -gt 0 ]]; then
  echo "⚠️  capture-observation failed $ERRORS_FOUND time(s) this session." >&2
  echo "   See last 3 errors:" >&2
  tail -n 3 "$ERROR_LOG" | sed 's/^/     /' >&2
  echo "   Likely cause: MCP / DB path broken. Run \`cos doctor\` to confirm." >&2
fi

if [[ "$OBS_COUNT" == "0" ]] && [[ "$WRITE_EDIT_COUNT" -gt 0 ]]; then
  echo "⚠️  ${WRITE_EDIT_COUNT} Write/Edit call(s) this session, 0 observations recorded —" >&2
  echo "   thinking_os memory did NOT learn from those edits. Check MCP wiring +" >&2
  echo "   DB path; run \`cos doctor\` to confirm." >&2
fi

if [[ "$OBS_COUNT" == "-1" ]]; then
  echo "⚠️  Could not query observations — DB missing or inaccessible at" >&2
  echo "   $COS_DB_PATH" >&2
fi

# Truncate the error log for the next session (keep it scoped).
if [[ -f "$ERROR_LOG" ]]; then
  : > "$ERROR_LOG"
fi
cos_log_hook check-capture-worked warn "observations=${OBS_COUNT} errors=${ERRORS_FOUND}"

exit 0
