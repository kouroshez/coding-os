#!/usr/bin/env bash
# SessionStart hook: Re-inject critical workflow context after compaction, resume, or startup.
# Agent-aware: session-id + volatile state live in COS_AGENT_DIR so two agents
# on the same project never share ephemeral state. Shared artifacts (DB, log)
# stay at COS_STATE_DIR. Full design in docs/engineering/state-files.md.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

# Resolve physical hooks dir — required for consumer projects where
# .claude/hooks/ is a real dir but each hook FILE is a symlink to
# core/hooks/. pwd -P only resolves symlinked directories, not files,
# so dirname+"$0" stays in .claude/hooks/ and ../thinking_os misses.
# BASH_SOURCE[0]+readlink follows the file symlink to its physical target.
_cos_src="${BASH_SOURCE[0]}"
while [ -L "$_cos_src" ]; do
  _cos_dir="$(cd -P "$(dirname "$_cos_src")" && pwd)"
  _cos_src="$(readlink "$_cos_src")"
  [[ "$_cos_src" != /* ]] && _cos_src="${_cos_dir}/${_cos_src}"
done
_COS_HOOKS_PHYS="$(cd -P "$(dirname "$_cos_src")" && pwd)"
unset _cos_src _cos_dir

INPUT="$(cos_read_stdin_bounded 2)"
COS_HOOK_RUNTIME_MODEL="$(printf '%s' "$INPUT" | jq -r '.model // empty' 2>/dev/null || true)"
export COS_HOOK_RUNTIME_MODEL

# Persist the model so hooks that don't receive it in stdin (PostToolUse
# that dispatches an async worker, CLI-originated task-done, etc.) can
# stamp task_outcomes.model and feed routing_weights.  File is truncated
# each write — only the latest signal matters.
if [[ -n "$COS_HOOK_RUNTIME_MODEL" ]] && [[ -n "${COS_AGENT_DIR:-}" ]]; then
  mkdir -p "$COS_AGENT_DIR" 2>/dev/null || true
  printf '%s' "$COS_HOOK_RUNTIME_MODEL" > "$COS_AGENT_DIR/.model" 2>/dev/null || true
fi
# SessionStart payloads carry `.source`; UserPromptSubmit carries `.prompt`.
# Treat prompt submits as their own source so Codex doesn't rotate session-id
# or clear volatile state on every prompt.
SOURCE=$(echo "$INPUT" | jq -r '
  if has("source") and (.source | type == "string") then .source
  elif has("prompt") then "user-prompt-submit"
  else "startup"
  end
' 2>/dev/null || echo "startup")
cos_log_hook session-context fire "source=${SOURCE}"

# Ensure BOTH dirs exist — COS_STATE_DIR for shared, COS_AGENT_DIR for per-agent.
mkdir -p "$COS_STATE_DIR" "$COS_AGENT_DIR"

# Refresh the .agent marker whenever cos-env.sh detected the runtime.
# Stale markers (e.g. `cursor` left over after switching to Claude) mis-route
# fallback paths in cos_retrieve / capture.py — rewrite on every session
# boundary so the *last* adapter to start is authoritative.
if [[ -n "${COS_AGENT:-}" ]] && [[ "$COS_AGENT" != "unknown" ]]; then
  _AGENT_MARKER="$COS_STATE_DIR/.agent"
  if [[ ! -f "$_AGENT_MARKER" ]] || [[ "$(cat "$_AGENT_MARKER" 2>/dev/null)" != "$COS_AGENT" ]]; then
    printf '%s' "$COS_AGENT" > "$_AGENT_MARKER" 2>/dev/null || true
    cos_log_hook session-context agent-refresh "agent=${COS_AGENT}"
  fi
  unset _AGENT_MARKER
fi

# Generate session ID ONLY on fresh startup — NOT on compact or resume.
if [[ "$SOURCE" == "startup" ]]; then
  # Orphan recovery: if the PREVIOUS session had observations but never got a
  # clean Stop, its session_summaries row was never built. We rebuild it
  # here before the ID is overwritten. session_summary.py is idempotent
  # (UPSERT) so this is a no-op when Stop fired cleanly.
  PREV_SESSION_ID=""
  if [ -f "$COS_SESSION_FILE" ]; then
    PREV_SESSION_ID=$(cat "$COS_SESSION_FILE" 2>/dev/null || true)
  fi

  if [ -n "$PREV_SESSION_ID" ] && [ -f "$COS_DB_PATH" ]; then
    SUMMARY_PY="${_COS_HOOKS_PHYS}/../thinking_os/session_summary.py"
    if [ -f "$SUMMARY_PY" ]; then
      python3 "$SUMMARY_PY" "$PREV_SESSION_ID" "" "$COS_DB_PATH" 2>/dev/null || true
      cos_log_hook session-context recovered "prev_session=${PREV_SESSION_ID}"
    fi
  fi

  # Session-id is agent-prefixed so logs and state files are self-describing.
  # Format: ses-<agent>-YYYYMMDD-HHMMSS-xxxx. Two agents on the same repo
  # get distinct ids and never inherit each other's state via string compare
  # in check-state.sh.
  SESSION_ID="ses-${COS_AGENT}-$(date +%Y%m%d-%H%M%S)-$(head -c 4 /dev/urandom | xxd -p | head -c 4)"
  echo "$SESSION_ID" > "$COS_SESSION_FILE"

  # Clear volatile markers from previous sessions. These files are either
  # session-scoped state or one-shot bypasses and must not bleed across chats.
  # Scope is THIS agent's private dir — the other agent's state is untouched.
  CLEARED=0
  for STATE_FILE in \
    "${COS_AGENT_DIR}/.thinking_os-gate" \
    "${COS_AGENT_DIR}/.task-current" \
    "${COS_AGENT_DIR}/.zoom-checkpoint" \
    "${COS_AGENT_DIR}/.active-skill" \
    "${COS_AGENT_DIR}/.doc-anchor" \
    "${COS_AGENT_DIR}/.memory-check" \
    "${COS_AGENT_DIR}/.learn-suggestions" \
    "${COS_AGENT_DIR}/.doc-anchor-override" \
    "${COS_AGENT_DIR}/.memory-check-override" \
    "${COS_AGENT_DIR}/.uv-heredoc-override" \
    "${COS_STATE_DIR}/.capture-errors.log"; do
    if [ -e "$STATE_FILE" ]; then
      rm -f "$STATE_FILE"
      CLEARED=$((CLEARED + 1))
    fi
  done
  cos_log_hook session-context reset "cleared=${CLEARED}"
fi

# On compact or resume: re-inject critical workflow reminders
if [[ "$SOURCE" == "compact" ]] || [[ "$SOURCE" == "resume" ]]; then
  printf '%s\n' \
    '[Session Context Recovery]' \
    '' \
    'CRITICAL WORKFLOW RULES:' \
    '1. Task management — use make commands, NEVER edit task files directly' \
    '2. Verification Matrix — run domain verification BEFORE marking done' \
    '3. Complexity Gate — record gate before writing code' \
    '4. Domain skill — invoke matching skill before writing code'
fi

# On startup: show active in-progress tasks (Phase L Scrumban) so the agent
# inherits open work without having to query the board first. Falls back to
# the legacy single-file `docs/tasks.md` only if the Phase L directory is
# absent (early-init projects).
if [[ "$SOURCE" == "startup" ]]; then
  WIP_LISTED=0
  if [ -d "docs/tasks" ] && [ -f "$COS_DB_PATH" ]; then
    # bash 5.3.9 deadlocks `$(python3 - <<HEREDOC)`. Form B (separate
    # .py file invoked as `python3 path/to/file.py`) is the only
    # deadlock-immune pattern. Resolve via readlink so symlinked install
    # paths still find _helpers/.
    _src="${BASH_SOURCE[0]}"
    while [ -L "$_src" ]; do
      _dir="$(cd -P "$(dirname "$_src")" && pwd)"
      _src="$(readlink "$_src")"
      [[ "$_src" != /* ]] && _src="$_dir/$_src"
    done
    HSRC="$(cd -P "$(dirname "$_src")" && pwd)"
    unset _src _dir
    WIP_HELPER="${HSRC}/_helpers/wip_lines.py"
    if [[ -f "$WIP_HELPER" ]]; then
      WIP_LINES=$(python3 "$WIP_HELPER" "$COS_DB_PATH" 2>/dev/null || true)
    else
      WIP_LINES=""
    fi
    if [ -n "$WIP_LINES" ]; then
      echo "[Session Start] Active tasks (in_progress / testing):"
      echo "$WIP_LINES"
      echo "  Resume with: cos task-show TASK-NNN  |  cos board"
      WIP_LISTED=1
    fi
  fi
  if [ "$WIP_LISTED" = "0" ] && [ -f "docs/tasks.md" ]; then
    WIP=$(grep '^\- \[/\]' docs/tasks.md 2>/dev/null | head -3 || true)
    if [ -n "$WIP" ]; then
      echo "[Session Start] In-progress tasks (legacy):"
      echo "$WIP" | while read -r line; do
        echo "  $line"
      done
    fi
  fi

  # Phase G.10 — Agent digest: print the rolling identity snapshot so the
  # agent inherits its beliefs/preferences across sessions. The file is
  # refreshed on every task-done; missing file (new project) is fine.
  DIGEST_PATH="${COS_STATE_DIR:-.coding-os}/digest.md"
  if [ -f "$DIGEST_PATH" ]; then
    echo ""
    echo "[Agent Digest]"
    cat "$DIGEST_PATH"
  fi

  # Phase EVO — Project Trajectory: inject latest trajectory snapshot so the
  # agent knows WHERE the project is heading (not just what tasks are open).
  # The trajectory section is already embedded in digest.md when present;
  # this helper also surfaces it as a standalone block for emphasis.
  if [ -f "$COS_DB_PATH" ]; then
    TRAJ_HELPER="${_COS_HOOKS_PHYS}/_helpers/trajectory_startup.py"
    if [ -f "$TRAJ_HELPER" ]; then
      python3 "$TRAJ_HELPER" "$COS_DB_PATH" 2>/dev/null || true
    fi
  fi

  # Phase EVO — Autonomous Routing Evolution: detect stale routing weights
  # and auto-trigger recalculate_weights when N=15 new outcomes accumulated.
  if [ -f "$COS_DB_PATH" ]; then
    ROUTING_HELPER="${_COS_HOOKS_PHYS}/_helpers/routing_evolution.py"
    if [ -f "$ROUTING_HELPER" ]; then
      python3 "$ROUTING_HELPER" "$COS_DB_PATH" 2>/dev/null || true
    fi
  fi

  # Token economics display — informational, non-blocking
  if [ -f "$COS_DB_PATH" ]; then
    STARTUP_PY="${_COS_HOOKS_PHYS}/../thinking_os/session_startup.py"
    if [ -f "$STARTUP_PY" ]; then
      python3 "$STARTUP_PY" "$COS_DB_PATH" 2>/dev/null || true
    fi
  fi
fi

exit 0
