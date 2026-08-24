#!/usr/bin/env bash
# PreToolUse hook: BLOCK Write/Edit on code files unless a matching domain skill has been invoked.
# Session-scoped: only accepts skills invoked in the CURRENT session.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(printf '%s' "$INPUT" | cos_json_field tool_name)

if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
  exit 0
fi

FILE_PATH=$(printf '%s' "$INPUT" | cos_json_field tool_input.file_path)

# Vendored, generated and agent-runtime trees are never gated, whatever they hold.
if [[ "$FILE_PATH" == *node_modules* ]] || [[ "$FILE_PATH" == *__pycache__* ]] || [[ "$FILE_PATH" == *.claude/* ]] || [[ "$FILE_PATH" == *.codex/* ]] || [[ "$FILE_PATH" == *.coding-os/* ]]; then
  exit 0
fi

# Two gated shapes. Code is matched by extension; prose a stranger reads
# outside the repo is matched by path, because the extension says nothing —
# a README is published prose, an ADR beside it is not. The test/spec skips
# stay off the prose leg deliberately: `*test*` also matches "latest", which
# would silently drop half a blog directory.
IS_PROSE=false
if [[ "$FILE_PATH" == README.md ]] || [[ "$FILE_PATH" == */README.md ]] || [[ "$FILE_PATH" == *docs/blog/*.md ]]; then
  IS_PROSE=true
fi

if [[ "$IS_PROSE" != "true" ]]; then
  if [[ "$FILE_PATH" != *.py ]] && [[ "$FILE_PATH" != *.ts ]] && [[ "$FILE_PATH" != *.tsx ]]; then
    exit 0
  fi
  # Skip test files, migrations, generated files
  if [[ "$FILE_PATH" == *test* ]] || [[ "$FILE_PATH" == *spec* ]] || [[ "$FILE_PATH" == *migrations* ]]; then
    exit 0
  fi
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
  echo '  README / blog → Skill skill: "humanizer"' >&2
  cos_log_hook enforce-skill block "rule=no-domain-skill" || true
  exit 2
fi

# Check skill matches file type (STATE_VALUE has all invoked skills)
ALL_SKILLS="$STATE_VALUE"

# Load-bearing guard: a file under the stack's graph.enforce_context_on globs
# (rag-config.yaml — the same per-consumer SSOT enforce-graph-context reads)
# REQUIRES graph-explorer; clean-code alone bypasses the graph layer and ships
# the dogfood gap. Data-driven (Rule 11): no path/stack literal lives here, so
# the verbatim-symlinked hook is correct in every consumer — an absent or empty
# list is simply a no-op (no false demand for a meta-only skill in a consumer).
if ! echo "$ALL_SKILLS" | grep -qiE "graph-explorer"; then
  GRAPH_CONFIG="${COS_STATE_DIR:-.coding-os}/rag-config.yaml"
  [[ -f "$GRAPH_CONFIG" ]] || GRAPH_CONFIG="$(pwd)/.coding-os/rag-config.yaml"
  if [[ -f "$GRAPH_CONFIG" ]]; then
    _src="${BASH_SOURCE[0]}"
    while [ -L "$_src" ]; do
      _dir="$(cd -P "$(dirname "$_src")" && pwd)"
      _src="$(readlink "$_src")"
      [[ "$_src" != /* ]] && _src="$_dir/$_src"
    done
    HSRC="$(cd -P "$(dirname "$_src")" && pwd)"
    unset _src _dir
    MATCH_HELPER="${HSRC}/_helpers/graph_context_match.py"
    if [[ -f "$MATCH_HELPER" ]] \
        && [[ "$(python3 "$MATCH_HELPER" "$GRAPH_CONFIG" "$FILE_PATH" 2>/dev/null || echo no)" == "yes" ]]; then
      echo "BLOCKED: $FILE_PATH is a graph-enforced load-bearing file (rag-config enforce_context_on) — Skill graph-explorer is required (clean-code alone bypasses the graph layer)." >&2
      echo "  Reason: structural edit on a load-bearing file — call cos_graph_context first." >&2
      echo "  Fix:    Skill skill: \"graph-explorer\"" >&2
      cos_log_hook enforce-skill block "rule=graph-explorer-required" || true
      exit 2
    fi
  fi
fi

if [[ "$IS_PROSE" == "true" ]]; then
  if ! echo "$ALL_SKILLS" | grep -qiE "humanizer"; then
    echo "BLOCKED: $FILE_PATH is prose a stranger reads outside the repo, and no skill invoked this session carries that judgment — text that trips AI tells costs the credibility of every claim it carries." >&2
    echo '  Fix: Skill skill: "humanizer"  (run technical-writing first when the deliverable is a document)' >&2
    cos_log_hook enforce-skill block "rule=humanizer-required" || true
    exit 2
  fi
fi

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
