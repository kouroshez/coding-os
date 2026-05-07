#!/usr/bin/env bash
# PreToolUse Write|Edit hook: require a Memory Check before code writes
# for COMPLICATED/COMPLEX tasks (thinking_os Orient phase).
#
# Rationale: the thinking_os skill mandates a ≤500-token memory check
# (`cos_search` / `cos_learn_suggest`) during Orient so the agent
# benefits from past patterns before implementing. Skipping it reverts
# every session to zero institutional memory.
#
# Mechanism: the agent records "I did the memory check" by calling
#   bash "$COS_AGENT_DIR/hooks/write-state.sh" "$COS_AGENT_DIR/.memory-check" "cos_search:<query>"
# once per session. This hook validates that marker exists. A future
# enhancement could auto-write this from inside the MCP server when
# cos_search is called, but the state-marker pattern keeps the hook
# layer pure shell (no MCP dependency) and matches existing markers
# like .thinking_os-gate / .zoom-checkpoint.
#
# Exemptions (no memory check required):
#   - CLEAR 1 classification (trivial ad-hoc fix)
#   - Task name contains exploratory|spike|experiment|scratch|governance|docs-update
#   - Non-code file paths
#   - tests/, migrations/, scaffold/, docs/, internal state dirs
#   - $COS_AGENT_DIR/.memory-check-override (one-shot bypass)
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
[[ -z "$FILE_PATH" ]] && exit 0

# Only enforce on code files. Docs/tests/scaffold/state are exempt.
case "$FILE_PATH" in
  *.py|*.ts|*.tsx|*.js|*.jsx|*.go|*.rs|*.rb) ;;
  *) exit 0 ;;
esac
BASENAME=$(basename "$FILE_PATH")
case "$BASENAME" in
  test_*|*_test.*|*.test.*|*.spec.*|conftest.py) exit 0 ;;
esac
case "$FILE_PATH" in
  */tests/*|*/migrations/*|*/__pycache__/*|*/node_modules/*) exit 0 ;;
  */.venv/*|*/.coding-os/*|*/.claude/*|*/.codex/*) exit 0 ;;
  */scaffold/*) exit 0 ;;
esac

# Persona-aware skip — see classify-task-mode.sh + docs/engineering/task-mode-matrix.md
MODE_FILE="${COS_AGENT_DIR}/.task-mode"
if [[ -f "$MODE_FILE" ]]; then
  TASK_MODE=$(tr -d '\n\r' < "$MODE_FILE" 2>/dev/null | head -c 24)
  case "$TASK_MODE" in
    query|adhoc|chore|system) exit 0 ;;
  esac
fi

COS_STATE_DIR="${COS_STATE_DIR:-.coding-os}"

# --- Exemptions via state files -------------------------------------
source "$(dirname "$0")/check-state.sh" 2>/dev/null || true

# CLEAR 1 gate — trivial ad-hoc fixes skip the memory check.
if type check_state >/dev/null 2>&1; then
  check_state "${COS_AGENT_DIR}/.thinking_os-gate" 7200
  if [[ "${STATE_VALID:-}" == "true" ]]; then
    CLASS=$(echo "${STATE_VALUE:-}" | awk '{print $1}')
    DIMS=$(echo "${STATE_VALUE:-}" | awk '{print $2}')
    if [[ "$CLASS" == "CLEAR" ]] && [[ "$DIMS" == "1" ]]; then
      exit 0
    fi
  fi
fi

# Exploratory/spike/governance tasks — skip.
if type check_state >/dev/null 2>&1; then
  check_state "${COS_AGENT_DIR}/.task-current" 28800
  if [[ "${STATE_VALID:-}" == "true" ]]; then
    TASK_NAME="${STATE_VALUE:-}"
    case "$TASK_NAME" in
      *exploratory*|*spike*|*experiment*|*scratch*|*governance*|*docs-update*)
        exit 0 ;;
    esac
  fi
fi

# One-shot override. Unified registry preferred; legacy
# $COS_AGENT_DIR/.memory-check-override still honoured.
if cos_one_shot_override memory-check 2>/dev/null; then
  exit 0
fi

# --- The check ------------------------------------------------------
MARKER="${COS_AGENT_DIR}/.memory-check"

if type check_state >/dev/null 2>&1; then
  # Session-scoped, 2h freshness.
  check_state "$MARKER" 7200
  if [[ "${STATE_VALID:-}" == "true" ]]; then
    exit 0
  fi
fi

# Block with a repair path.
echo "BLOCKED: Memory Check not recorded for this session." >&2
echo "  Rule: COMPLICATED/COMPLEX tasks must query memory in Orient." >&2
echo "  File attempted: $FILE_PATH" >&2
echo "" >&2
echo "  Repair (pick one):" >&2
echo "  1. Call cos_search in this session, then mark:" >&2
echo "       bash \"\$COS_AGENT_DIR/hooks/write-state.sh\" \"\$COS_AGENT_DIR/.memory-check\" \"cos_search:<your-query>\"" >&2
echo "  2. Trivial ad-hoc fix → record CLEAR 1 gate instead:" >&2
echo "       bash \"\$COS_AGENT_DIR/hooks/write-state.sh\" \"\$COS_AGENT_DIR/.thinking_os-gate\" \"CLEAR 1\"" >&2
echo "  3. Exploratory spike → rename task marker:" >&2
echo "       bash \"\$COS_AGENT_DIR/hooks/write-state.sh\" \"\$COS_AGENT_DIR/.task-current\" \"exploratory-<slug>\"" >&2
echo "" >&2
echo "  One-shot bypass: touch ${COS_AGENT_DIR}/.memory-check-override" >&2
exit 2
