#!/usr/bin/env bash
# PreToolUse Edit|Write — subagent-delegation nudge for large audits.
#
# When intent.exhaustive=true AND the active audit has ≥5 categories,
# warn once per session that per-category sweep work SHOULD be
# delegated to read-only Explore subagents so the main session
# preserves context for synthesis.  Without delegation, deep audits
# fill the main context and the agent compresses, dropping findings.
#
# Default: WARN only (exit 0 with stderr).  Strict mode
# (COS_ENFORCE_SUBAGENT_DELEGATION=strict): BLOCK when no Agent /
# Task tool call appears in the session's hooks.log.  Opt-in only —
# strict-by-default would block small audits where delegation is
# overkill.
#
# Skip conditions match enforce-count-grounding for consistency.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_require_or_skip jq enforce-subagent-delegation

INPUT="$(cos_read_stdin_bounded 2)"
if [[ -z "$INPUT" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

case "$FILE_PATH" in
  */docs/tasks/audits/*|docs/tasks/audits/*) exit 0 ;;
  */docs/_meta/*|docs/_meta/*) exit 0 ;;
  */.coding-os/*|.coding-os/*) exit 0 ;;
  /tmp/*|*/tmp/*) exit 0 ;;
esac
case "$FILE_PATH" in
  */src/*|src/*) ;;
  *) exit 0 ;;
esac

INTENT_FILE="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.intent.json"  # panel-first (TASK-107)
[[ -f "$INTENT_FILE" ]] || INTENT_FILE="${COS_AGENT_DIR}/.intent.json"
if [[ ! -f "$INTENT_FILE" ]]; then
  exit 0
fi
EXHAUSTIVE=$(jq -r '.exhaustive // false' "$INTENT_FILE" 2>/dev/null || echo "false")
if [[ "$EXHAUSTIVE" != "true" ]]; then
  exit 0
fi

MARKER="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.subagent-delegation-nudged"  # panel-first (TASK-107)
if [[ -f "$MARKER" ]]; then
  exit 0
fi

# Count categories in the first active audit file. <5 → no enforcement.
AUDIT_DIR="docs/tasks/audits"
CATEGORY_COUNT=0
ACTIVE_FILE=""
if [[ -d "$AUDIT_DIR" ]]; then
  AUDIT_FILES=$(compgen -G "${AUDIT_DIR}/audit-*.md" 2>/dev/null || true)
  if [[ -n "$AUDIT_FILES" ]]; then
    # Match BOTH YAML (template canonical) and markdown bold (historic)
    # forms — mirrors session-context.sh / enforce-audit-artifact.sh.
    ACTIVE_FILE=$(grep -lE "(^status:[[:space:]]+in_progress|\*\*Status:\*\*[[:space:]]+in_progress)" $AUDIT_FILES 2>/dev/null | head -1 || true)
    if [[ -n "$ACTIVE_FILE" ]]; then
      # Data rows start with `| <number> |` — count them.
      CATEGORY_COUNT=$(grep -cE '^\|\s*[0-9]+\s*\|' "$ACTIVE_FILE" 2>/dev/null || echo 0)
    fi
  fi
fi
if [[ "$CATEGORY_COUNT" -lt 5 ]]; then
  exit 0
fi

# Heuristic detection of subagent call: any Agent/Task line in hooks log.
HAS_SUBAGENT=0
if [[ -f "$COS_HOOK_LOG" ]] && grep -qE "(subagent|SubagentStart|Agent .*tool|Task tool)" "$COS_HOOK_LOG" 2>/dev/null; then
  HAS_SUBAGENT=1
fi
if [[ "$HAS_SUBAGENT" -eq 1 ]]; then
  touch "$MARKER" 2>/dev/null || true
  exit 0
fi

cos_log_hook enforce-subagent-delegation nudge "categories=${CATEGORY_COUNT} audit=${ACTIVE_FILE}"
touch "$MARKER" 2>/dev/null || true

MSG="subagent-delegation reminder — audit ${ACTIVE_FILE} declares ${CATEGORY_COUNT} categories.

  For audits of this scale, per-category sweep work SHOULD be delegated
  to read-only Explore subagents:
    Agent(subagent_type='Explore',
          description='sweep category X',
          prompt='grep for <pattern> across src/, report file:line list under 200 words')

  Each subagent runs in its own context — findings come back compact,
  and the main session keeps its context budget for synthesis.
  Without delegation, deep audits fill the main context and the agent
  compresses, dropping findings — the very failure mode this layer
  exists to prevent.

  This is a soft warning (once per session).  Hard block:
  export COS_ENFORCE_SUBAGENT_DELEGATION=strict."

if [[ "${COS_ENFORCE_SUBAGENT_DELEGATION:-warn}" == "strict" ]]; then
  echo "BLOCKED: ${MSG}" >&2
  exit 2
fi

echo "warning: ${MSG}" >&2
exit 0
