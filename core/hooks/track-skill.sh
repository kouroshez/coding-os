#!/usr/bin/env bash
# PostToolUse hook: Track which skill was invoked by writing to $COS_AGENT_DIR/.active-skill.
# Session-scoped: prefixes with current session ID.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')

# Only track Skill tool invocations
if [[ "$TOOL" != "Skill" ]]; then
  exit 0
fi

SKILL_NAME=$(echo "$INPUT" | jq -r '.tool_input.skill // empty')

if [[ -n "$SKILL_NAME" ]]; then
  SESSION_FILE="$COS_SESSION_FILE"
  SESSION_ID=""
  if [[ -f "$SESSION_FILE" ]]; then
    SESSION_ID=$(cat "$SESSION_FILE")
  fi
  # Write session-scoped: "session-id skill1 skill2 ..."
  # Append skill to existing value if same session, else reset
  SKILL_FILE="${COS_AGENT_DIR}/.active-skill"
  mkdir -p "$COS_AGENT_DIR" 2>/dev/null || true
  if [[ -f "$SKILL_FILE" ]]; then
    EXISTING_SESSION=$(head -1 "$SKILL_FILE" | awk '{print $1}')
    if [[ "$EXISTING_SESSION" == "$SESSION_ID" ]]; then
      # Same session — append skill
      EXISTING_SKILLS=$(head -1 "$SKILL_FILE" | cut -d' ' -f2-)
      echo "$SESSION_ID $EXISTING_SKILLS $SKILL_NAME" > "$SKILL_FILE"
      exit 0
    fi
  fi
  # New session or no file — start fresh
  echo "$SESSION_ID $SKILL_NAME" > "$SKILL_FILE"
fi

exit 0
