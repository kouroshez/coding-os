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

INPUT=""
if [[ ! -t 0 ]]; then
  INPUT=$(cat 2>/dev/null || true)
fi

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

# Delegate JSON read/merge/write to Python so we preserve prior fields
# across events (e.g. a Stop must not clobber started_at).
python3 - "$PRESENCE_FILE" "$COS_AGENT" "$SESSION_ID" "$AGENT_PID" "$EVENT" "$NOW" <<'PY' 2>/dev/null || exit 0
import json, os, sys

path, agent, sid, pid, event, now_s = sys.argv[1:]
pid = int(pid)
now = int(now_s)

prev = {}
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as f:
            prev = json.load(f)
    except (OSError, json.JSONDecodeError):
        prev = {}

new = {
    "agent": agent,
    "session_id": sid,
    "pid": pid,
    "started_at": prev.get("started_at"),
    "last_prompt_at": prev.get("last_prompt_at"),
    "last_tool_at": prev.get("last_tool_at"),
    "last_stop_at": prev.get("last_stop_at"),
    "ended_at": prev.get("ended_at"),
}

if event == "start":
    new["started_at"] = now
    new["ended_at"] = None
    new["last_stop_at"] = None
elif event == "prompt":
    new["last_prompt_at"] = now
    new["last_stop_at"] = None
    new["started_at"] = new["started_at"] or now
elif event == "tool":
    new["last_tool_at"] = now
    new["started_at"] = new["started_at"] or now
elif event == "stop":
    new["last_stop_at"] = now
elif event == "end":
    new["ended_at"] = now

tmp = f"{path}.tmp.{os.getpid()}"
with open(tmp, "w", encoding="utf-8") as f:
    json.dump(new, f, separators=(",", ":"))
os.replace(tmp, path)
PY

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
python3 - "$PRESENCE_DIR" "$NOW" <<'PY' 2>/dev/null || true
import json, os, sys
d, now = sys.argv[1], int(sys.argv[2])
if not os.path.isdir(d):
    sys.exit(0)
for name in os.listdir(d):
    if not name.endswith(".json"):
        continue
    p = os.path.join(d, name)
    try:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        try:
            if now - os.path.getmtime(p) > 3600:
                os.unlink(p)
        except OSError:
            pass
        continue
    ended = data.get("ended_at")
    if isinstance(ended, int) and now - ended > 3600:
        try:
            os.unlink(p)
        except OSError:
            pass
PY
fi

cos_log_hook agent-presence fire "event=${EVENT}" 2>/dev/null || true
exit 0
