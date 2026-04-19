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
COS_STATE_DIR="${COS_STATE_DIR:-.coding-os}"
COS_DB_PATH="${COS_DB_PATH:-$COS_STATE_DIR/thinking-os.db}"
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
  OBS_COUNT=$(python3 - "$COS_DB_PATH" "$SESSION_ID" <<'PY' 2>/dev/null || echo -1
import sqlite3, sys
try:
    conn = sqlite3.connect(sys.argv[1], timeout=2)
    cur = conn.execute(
        "SELECT COUNT(*) FROM observations WHERE session_id = ?",
        (sys.argv[2],),
    )
    print(cur.fetchone()[0])
    conn.close()
except Exception:
    print(-1)
PY
  )
fi

# --- 3. Decide what to say ------------------------------------------
# Silent success path: no errors AND observations > 0 → nothing to say.
if [[ "$ERRORS_FOUND" == "0" ]] && [[ "$OBS_COUNT" -gt 0 ]]; then
  cos_log_hook check-capture-worked ok "observations=${OBS_COUNT}"
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

if [[ "$OBS_COUNT" == "0" ]]; then
  echo "⚠️  Zero observations recorded — thinking-os memory did NOT learn" >&2
  echo "   from this session. Check MCP wiring + DB path before next session." >&2
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
