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
if [[ "$FILE_PATH" == *test* ]] || [[ "$FILE_PATH" == *spec* ]] || [[ "$FILE_PATH" == *migrations* ]] || [[ "$FILE_PATH" == *node_modules* ]] || [[ "$FILE_PATH" == *__pycache__* ]] || [[ "$FILE_PATH" == *.claude/* ]] || [[ "$FILE_PATH" == *.codex/* ]] || [[ "$FILE_PATH" == *.coding-os/* ]]; then
  exit 0
fi

# Persona-aware skip — see classify-task-mode.sh + docs/engineering/task-mode-matrix.md
MODE_FILE="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.task-mode"  # panel-first
[[ -f "$MODE_FILE" ]] || MODE_FILE="${COS_AGENT_DIR}/.task-mode"
if [[ -f "$MODE_FILE" ]]; then
  TASK_MODE=$(tr -d '\n\r' < "$MODE_FILE" 2>/dev/null | head -c 24)
  case "$TASK_MODE" in
    query|adhoc|chore|system) exit 0 ;;
  esac
fi

# Panel-first: track-skill.sh writes .active-skill to
# $COS_PANEL_DIR, but this read used only $COS_AGENT_DIR — so the
# per-panel marker was never found and every non-CLEAR-1 edit blocked.
# Mirror the gate read below (which already uses COS_PANEL_DIR).
SKILL_FILE="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.active-skill"

# Skip skill gate during formula dispatches other than implementer/reviewer.
# The supervisor writes .active-formula before each dispatch; implementer
# and reviewer are the only roles that actually write domain code.
ACTIVE_FORMULA_FILE="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.active-formula"  # panel-first: written to + cleared from the panel dir
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
  echo "BLOCKED: a domain skill carries the judgment this edit needs — code written without it ships debt. No domain skill invoked for this session. Reason: $STATE_REASON" >&2
  echo '  Backend .py  → Skill skill: "python-django"' >&2
  echo '  Frontend .tsx → Skill skill: "nextjs-react"' >&2
  echo '  Any code     → Skill skill: "clean-code"' >&2
  cos_log_hook enforce-skill block "rule=no-domain-skill" || true
  exit 2
fi

# Check skill matches file type (STATE_VALUE has all invoked skills)
ALL_SKILLS="$STATE_VALUE"

# Meta-stack guard: editing a meta-repo authoring path REQUIRES the
# graph-explorer skill (clean-code alone is not enough) — closes the dogfood
# gap where the agent bypasses graph by loading only clean-code. SSOT:
# src/templates/meta/stack.yaml::skill_enforcement.
#
# Meta-scope gate (TASK-474 P4-14/15): the hook is symlinked verbatim into
# consumers, where `*core/*.py` would wrongly match the consumer's OWN
# src/core/*.py and demand a meta-only skill. Fire ONLY inside the coding-os
# source tree, and self-skip when the graph module is disabled (the skill is gone).
_in_meta_source_tree() {
  local dir
  dir=$(cd "$(dirname "$1")" 2>/dev/null && pwd) || return 1
  while [[ "$dir" != "/" && -n "$dir" ]]; do
    if [[ -d "$dir/src/templates/_base" && -d "$dir/src/adapters/claude" \
          && -d "$dir/src/adapters/codex" ]]; then
      return 0
    fi
    dir=$(dirname "$dir")
  done
  return 1
}

_graph_module_disabled() {
  local state="${COS_STATE_DIR:-.coding-os}/subsystems-state.json"
  [[ -f "$state" ]] || state="$(pwd)/.coding-os/subsystems-state.json"
  [[ -f "$state" ]] || return 1
  jq -e '(.disabled // []) | index("graph") != null' "$state" >/dev/null 2>&1
}

case "$FILE_PATH" in
  *core/*.py|*cli/*.py|*adapters/*.py)
    if _in_meta_source_tree "$FILE_PATH" && ! _graph_module_disabled \
        && ! echo "$ALL_SKILLS" | grep -qiE "graph-explorer"; then
      echo "BLOCKED: Editing meta-repo authoring path ($FILE_PATH) requires Skill graph-explorer." >&2
      echo "  Reason: load-bearing src/core/cli/adapter file — call cos_graph_context first." >&2
      echo "  Fix:    Skill skill: \"graph-explorer\"" >&2
      cos_log_hook enforce-skill block "rule=graph-explorer-required" || true
      exit 2
    fi
    ;;
esac

if [[ "$FILE_PATH" == *.py ]]; then
  if ! echo "$ALL_SKILLS" | grep -qiE "python|django|clean-code|graph-explorer"; then
    echo "BLOCKED: Writing .py file but no matching skill invoked. Invoke python-django, clean-code, or graph-explorer first." >&2
    cos_log_hook enforce-skill block "rule=py-skill-required" || true
    exit 2
  fi
fi

if [[ "$FILE_PATH" == *.ts ]] || [[ "$FILE_PATH" == *.tsx ]]; then
  if ! echo "$ALL_SKILLS" | grep -qiE "nextjs|react|clean-code|frontend|tailwind"; then
    echo "BLOCKED: Writing .ts/.tsx file but no matching skill invoked. Invoke nextjs-react or clean-code first." >&2
    cos_log_hook enforce-skill block "rule=ts-skill-required" || true
    exit 2
  fi
fi

exit 0
