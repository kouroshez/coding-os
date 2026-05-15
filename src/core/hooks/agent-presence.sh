#!/usr/bin/env bash
# Coding OS — agent-presence.sh
#
# PURPOSE
#   Maintain a per-session presence file so the board UI can tell in
#   real time whether an agent is:
#     • ACTIVE   — tool call within the last 30s or user turn in flight
#     • PRESENT  — session alive, PID still running, no recent tool
#     • OFFLINE  — no session marker / PID dead / Stop emitted long ago
#
#   The hook layer is the only cross-agent signal we have for presence:
#   Claude Code, Cursor, and Codex all fire shell hooks via their
#   settings.{json,toml} contract.  Every lifecycle event routes to
#   this one script so the state file has a single writer, which keeps
#   the concurrency model trivial (tmp file + atomic rename).
#
# INVOKED BY
#   A single registry.yaml entry maps this script to every lifecycle
#   event Claude/Cursor/Codex expose.  The script reads `hook_event_name`
#   from the JSON payload Claude Code sends on stdin and routes to the
#   correct action:
#     SessionStart    → "start"
#     UserPromptSubmit→ "prompt"
#     PreToolUse      → "tool"
#     PostToolUse     → "tool"
#     Stop            → "stop"
#     SessionEnd      → "end"   (Claude Code 2.x; optional)
#
# OUTPUT
#   $COS_AGENT_DIR/sessions/<session_id>.json (one file per live session).
#     {
#       "agent":            "claude|cursor|codex",
#       "session_id":       "ses-<agent>-YYYYMMDD-...",
#       "pid":              <integer>,     // agent runtime pid
#       "started_at":       <epoch>,
#       "last_prompt_at":   <epoch|null>,
#       "last_tool_at":     <epoch|null>,
#       "last_stop_at":     <epoch|null>,
#       "ended_at":         <epoch|null>
#     }
#   Files whose ended_at is >1h old get garbage-collected lazily.
#
# DESIGN NOTES
#   - Fail-open: every error path exits 0 so presence tracking never
#     blocks an agent's tool call.
#   - PID is the hook's parent ($PPID) — that's the agent runtime
#     itself.  board.py's `_pid_alive` uses `os.kill(pid, 0)` to detect
#     a crashed session that never got to emit SessionEnd.
#   - JSON writes go through a tmp file + `mv -f` so concurrent readers
#     never see a half-written file.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi


# bash 5.3.9 sporadically deadlocks `INPUT=$(cat)` (any $() with stdin).
# `cos_read_stdin_bounded` uses perl alarm — bounded read, never hangs.
INPUT="$(cos_read_stdin_bounded 2)"

# Derive the logical event.  Prefer the explicit hook_event_name field
# Claude Code sends; fall back to `$1` so the script stays testable
# from the CLI (e.g. `bash agent-presence.sh start`).
EVENT_RAW=""
if [[ -n "$INPUT" ]]; then
  EVENT_RAW=$(printf '%s' "$INPUT" | jq -r '.hook_event_name // empty' 2>/dev/null || true)
fi
if [[ -z "$EVENT_RAW" ]]; then
  EVENT_RAW="${1:-}"
fi

case "$EVENT_RAW" in
  SessionStart|start)      EVENT="start" ;;
  UserPromptSubmit|prompt) EVENT="prompt" ;;
  PreToolUse|PostToolUse|tool) EVENT="tool" ;;
  PostToolUseFailure)      EVENT="tool" ;;   # tool errored — still recent activity
  SubagentStart)           EVENT="tool" ;;   # sub-session spawn: parent is active
  SubagentStop)            EVENT="tool" ;;   # sub-session done: parent activity
  Stop|stop)               EVENT="stop" ;;
  SessionEnd|end)          EVENT="end" ;;
  *)                       EVENT="tool" ;;   # safest default: count as activity
esac

PRESENCE_DIR="${COS_AGENT_DIR}/sessions"
mkdir -p "$PRESENCE_DIR" 2>/dev/null || exit 0

if [[ ! -f "$COS_SESSION_FILE" ]]; then
  exit 0
fi
SESSION_ID="$(cat "$COS_SESSION_FILE" 2>/dev/null | tr -d '[:space:]' || true)"
[[ -z "$SESSION_ID" ]] && exit 0
# Defense-in-depth — the session-id file is one we write, but it lives
# in a per-agent directory any runtime can touch.  Reject anything that
# couldn't be a filename so PRESENCE_FILE can never escape sessions/.
if ! [[ "$SESSION_ID" =~ ^[A-Za-z0-9_-]+$ ]]; then
  cos_log_hook agent-presence warn "rejected session id with invalid chars" 2>/dev/null || true
  exit 0
fi

# PPID is the agent runtime; a later `kill -0 $pid` from board.py proves
# the session is alive even when no hook has fired for minutes.
AGENT_PID="${PPID:-$$}"
NOW="$(date +%s)"
PRESENCE_FILE="${PRESENCE_DIR}/${SESSION_ID}.json"

# Delegate JSON merge to a separate helper. Inline `python3 - <<'PY'`
# sporadically deadlocks in heredoc_write on bash 5.3.9 — and this hook
# fires on every tool call, so even rare hangs accumulate dozens of
# zombies that starve agent runtime spawns. Form B (separate .py)
# is the only deadlock-immune pattern. Resolve via readlink so symlinked
# install paths still find _helpers/.
_src="${BASH_SOURCE[0]}"
while [ -L "$_src" ]; do
  _dir="$(cd -P "$(dirname "$_src")" && pwd)"
  _src="$(readlink "$_src")"
  [[ "$_src" != /* ]] && _src="$_dir/$_src"
done
COS_HOOK_SRC_DIR="$(cd -P "$(dirname "$_src")" && pwd)"
unset _src _dir

PRESENCE_HELPER="${COS_HOOK_SRC_DIR}/_helpers/presence_write.py"
if [[ -f "$PRESENCE_HELPER" ]]; then
  python3 "$PRESENCE_HELPER" \
    "$PRESENCE_FILE" "$COS_AGENT" "$SESSION_ID" "$AGENT_PID" "$EVENT" "$NOW" \
    2>/dev/null || true
fi

# Lazy GC — drop presence files whose session ended >1h ago.
# The hook fires on every tool call; running the GC scan every time adds
# noticeable overhead on busy sessions (python3 startup + readdir + stat).
# Throttle to once per ~60s: cheap-enough to forget, rare-enough to skip.
GC_TICK=$((NOW / 60))
GC_MARKER="${PRESENCE_DIR}/.gc-tick"
RUN_GC=0
if [[ ! -f "$GC_MARKER" ]] || [[ "$(cat "$GC_MARKER" 2>/dev/null)" != "$GC_TICK" ]]; then
  echo "$GC_TICK" > "$GC_MARKER" 2>/dev/null || true
  RUN_GC=1
fi
if [[ "$RUN_GC" == "1" ]]; then
  GC_HELPER="${COS_HOOK_SRC_DIR}/_helpers/presence_gc.py"
  if [[ -f "$GC_HELPER" ]]; then
    python3 "$GC_HELPER" "$PRESENCE_DIR" "$NOW" 2>/dev/null || true
  fi
fi

cos_log_hook agent-presence fire "event=${EVENT}" 2>/dev/null || true
exit 0
