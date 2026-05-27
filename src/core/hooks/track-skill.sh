#!/usr/bin/env bash
# PostToolUse hook: Track which skill was invoked by writing to
# $COS_PANEL_DIR/.active-skill (per-panel since TASK-035 — two Claude tabs
# track their own skill stacks independently).
# Session-scoped: prefixes with current session ID.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

# Upgrade panel-id from stdin so sibling Claude panels don't collide.
INPUT="$(cos_read_stdin_bounded 2)"
cos_panel_upgrade_from_payload "$INPUT" 2>/dev/null || true

TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")

# Only track Skill tool invocations
if [[ "$TOOL" != "Skill" ]]; then
  exit 0
fi

SKILL_NAME=$(echo "$INPUT" | jq -r '.tool_input.skill // empty' 2>/dev/null || echo "")

if [[ -n "$SKILL_NAME" ]]; then
  SESSION_FILE="$COS_SESSION_FILE"
  SESSION_ID=""
  if [[ -f "$SESSION_FILE" ]]; then
    SESSION_ID=$(cat "$SESSION_FILE")
  fi
  # Fall back to panel-id when session-id file is empty (fresh panel,
  # SessionStart never fired yet).
  [[ -z "$SESSION_ID" && -n "${COS_PANEL_ID:-}" ]] && SESSION_ID="$COS_PANEL_ID"
  # Write session-scoped: "session-id skill1 skill2 ..."
  # Append skill to existing value if same session, else reset.
  SKILL_FILE="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.active-skill"
  mkdir -p "$(dirname "$SKILL_FILE")" 2>/dev/null || true
  if [[ -f "$SKILL_FILE" ]]; then
    EXISTING_SESSION=$(head -1 "$SKILL_FILE" | awk '{print $1}')
    if [[ "$EXISTING_SESSION" == "$SESSION_ID" ]]; then
      # Same session — append skill
      EXISTING_SKILLS=$(head -1 "$SKILL_FILE" | cut -d' ' -f2-)
      echo "$SESSION_ID $EXISTING_SKILLS $SKILL_NAME" > "$SKILL_FILE"
      cos_record_activity skill "${SKILL_NAME}" 2>/dev/null || true
      printf '{"systemMessage":%s}' "$(printf '[skill] %s' "$SKILL_NAME" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
      exit 0
    fi
  fi
  # New session or no file — start fresh
  echo "$SESSION_ID $SKILL_NAME" > "$SKILL_FILE"
  cos_record_activity skill "${SKILL_NAME}" 2>/dev/null || true
  printf '{"systemMessage":%s}' "$(printf '[skill] %s' "$SKILL_NAME" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
fi

exit 0
