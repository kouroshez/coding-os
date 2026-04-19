#!/usr/bin/env bash
# SessionStart hook: Re-inject critical workflow context after compaction, resume, or startup.
# Agent-aware: session-id + volatile state live in COS_AGENT_DIR so two agents
# on the same project never share ephemeral state. Shared artifacts (DB, log)
# stay at COS_STATE_DIR. Full design in docs/engineering/state-files.md.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

INPUT=$(cat)
# SessionStart payloads carry `.source`; UserPromptSubmit carries `.prompt`.
# Treat prompt submits as their own source so Codex doesn't rotate session-id
# or clear volatile state on every prompt.
SOURCE=$(echo "$INPUT" | jq -r '
  if has("source") and (.source | type == "string") then .source
  elif has("prompt") then "user-prompt-submit"
  else "startup"
  end
')
cos_log_hook session-context fire "source=${SOURCE}"

# Ensure BOTH dirs exist — COS_STATE_DIR for shared, COS_AGENT_DIR for per-agent.
mkdir -p "$COS_STATE_DIR" "$COS_AGENT_DIR"

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
    for SCRIPT_DIR in "$(dirname "$0")/../thinking-os" ".claude/thinking-os"; do
      if [ -f "${SCRIPT_DIR}/session_summary.py" ]; then
        python3 "${SCRIPT_DIR}/session_summary.py" "$PREV_SESSION_ID" "" "$COS_DB_PATH" 2>/dev/null || true
        cos_log_hook session-context recovered "prev_session=${PREV_SESSION_ID}"
        break
      fi
    done
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
    "${COS_AGENT_DIR}/.thinking-os-gate" \
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

# On startup: show active task context + token economics
if [[ "$SOURCE" == "startup" ]]; then
  if [ -f "docs/tasks.md" ]; then
    WIP=$(grep '^\- \[/\]' docs/tasks.md 2>/dev/null | head -3 || true)
    if [ -n "$WIP" ]; then
      echo "[Session Start] In-progress tasks found:"
      echo "$WIP" | while read -r line; do
        echo "  $line"
      done
      echo "  Resume with: make task-context TASK=<num>"
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

  # Token economics display — informational, non-blocking
  if [ -f "$COS_DB_PATH" ]; then
    # Look for startup script in coding-os core or .claude
    for SCRIPT_DIR in "$(dirname "$0")/../thinking-os" ".claude/thinking-os"; do
      STARTUP_SCRIPT="${SCRIPT_DIR}/session_startup.py"
      if [ -f "$STARTUP_SCRIPT" ]; then
        COS_DB_PATH="$COS_DB_PATH" python3 "$STARTUP_SCRIPT" "$COS_DB_PATH" 2>/dev/null || true
        break
      fi
    done
  fi
fi
