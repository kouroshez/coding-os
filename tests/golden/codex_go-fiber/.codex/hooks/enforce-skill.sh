#!/usr/bin/env bash
# PreToolUse hook: BLOCK Write/Edit on code files unless a matching domain skill has been invoked.
# Session-scoped: only accepts skills invoked in the CURRENT session.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")

if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")

# Only enforce for code files
if [[ "$FILE_PATH" != *.py ]] && [[ "$FILE_PATH" != *.ts ]] && [[ "$FILE_PATH" != *.tsx ]]; then
  exit 0
fi

# Skip test files, migrations, generated files, config files, hook scripts
if [[ "$FILE_PATH" == *test* ]] || [[ "$FILE_PATH" == *spec* ]] || [[ "$FILE_PATH" == *migrations* ]] || [[ "$FILE_PATH" == *node_modules* ]] || [[ "$FILE_PATH" == *__pycache__* ]] || [[ "$FILE_PATH" == *.claude/* ]] || [[ "$FILE_PATH" == *.codex/* ]] || [[ "$FILE_PATH" == *.cursor/* ]] || [[ "$FILE_PATH" == *.coding-os/* ]]; then
  exit 0
fi

# Persona-aware skip — see classify-task-mode.sh + docs/engineering/task-mode-matrix.md
MODE_FILE="${COS_AGENT_DIR}/.task-mode"
if [[ -f "$MODE_FILE" ]]; then
  TASK_MODE=$(tr -d '\n\r' < "$MODE_FILE" 2>/dev/null | head -c 24)
  case "$TASK_MODE" in
    query|adhoc|chore|system) exit 0 ;;
  esac
fi

# Panel-first (TASK-035): track-skill.sh writes .active-skill to
# $COS_PANEL_DIR, but this read used only $COS_AGENT_DIR — so the
# per-panel marker was never found and every non-CLEAR-1 edit blocked.
# Mirror the gate read below (which already uses COS_PANEL_DIR).
SKILL_FILE="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.active-skill"

# Phase M: skip skill gate during formula dispatches other than implementer/reviewer.
# The supervisor writes .active-formula before each dispatch; implementer
# and reviewer are the only roles that actually write domain code.
ACTIVE_FORMULA_FILE="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.active-formula"  # panel-first (TASK-035): written to + cleared from the panel dir
if [[ -f "$ACTIVE_FORMULA_FILE" ]]; then
  ACTIVE_FORMULA=$(cat "$ACTIVE_FORMULA_FILE" 2>/dev/null || echo "")
  if [[ "$ACTIVE_FORMULA" != "implementer" && "$ACTIVE_FORMULA" != "reviewer" && -n "$ACTIVE_FORMULA" ]]; then
    exit 0
  fi
fi

# Allow CLEAR 1 ad-hoc fixes without a skill (same fast-path as enforce-task-start.sh)
source "$(dirname "$0")/check-state.sh"
check_state "${COS_PANEL_DIR:-$COS_AGENT_DIR}/.thinking_os-gate" 7200
if [[ "$STATE_VALID" == "true" ]]; then
  CLASSIFICATION=$(echo "$STATE_VALUE" | awk '{print $1}')
  DIMS=$(echo "$STATE_VALUE" | awk '{print $2}')
  if [[ "$CLASSIFICATION" == "CLEAR" ]] && [[ "$DIMS" == "1" ]]; then
    exit 0
  fi
fi

# Check existence and session scope
check_state "$SKILL_FILE" 7200  # 120 min

if [[ "$STATE_VALID" != "true" ]]; then
  echo "BLOCKED: No domain skill invoked for this session. Reason: $STATE_REASON" >&2
  echo '  Backend .py  → Skill skill: "python-django"' >&2
  echo '  Frontend .tsx → Skill skill: "nextjs-react"' >&2
  echo '  Any code     → Skill skill: "clean-code"' >&2
  exit 2
fi

# Check skill matches file type (STATE_VALUE has all invoked skills)
ALL_SKILLS="$STATE_VALUE"

# Meta-stack guard: editing any meta-repo authoring path REQUIRES the
# graph-explorer skill (clean-code alone is not enough). This closes
# the dogfood gap where the agent could bypass graph by loading only
# clean-code. Source of truth: src/templates/meta/stack.yaml::skill_enforcement.
case "$FILE_PATH" in
  *core/*.py|*cli/*.py|*adapters/*.py)
    if ! echo "$ALL_SKILLS" | grep -qiE "graph-explorer"; then
      echo "BLOCKED: Editing meta-repo authoring path ($FILE_PATH) requires Skill graph-explorer." >&2
      echo "  Reason: load-bearing src/core/cli/adapter file — call cos_graph_context first." >&2
      echo "  Fix:    Skill skill: \"graph-explorer\"" >&2
      exit 2
    fi
    ;;
esac

if [[ "$FILE_PATH" == *.py ]]; then
  if ! echo "$ALL_SKILLS" | grep -qiE "python|django|clean-code|graph-explorer"; then
    echo "BLOCKED: Writing .py file but no matching skill invoked. Invoke python-django, clean-code, or graph-explorer first." >&2
    exit 2
  fi
fi

if [[ "$FILE_PATH" == *.ts ]] || [[ "$FILE_PATH" == *.tsx ]]; then
  if ! echo "$ALL_SKILLS" | grep -qiE "nextjs|react|clean-code|frontend|tailwind"; then
    echo "BLOCKED: Writing .ts/.tsx file but no matching skill invoked. Invoke nextjs-react or clean-code first." >&2
    exit 2
  fi
fi

exit 0
