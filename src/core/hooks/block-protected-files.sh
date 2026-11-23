#!/usr/bin/env bash
# PreToolUse hook: Block direct edits to protected files.
# Protected:
#   - changes.log (use make log-write)
#   - Governance files: agent rules/, hooks/, CLAUDE.md, AGENTS.md,
#     infrastructure/scripts/ — never edit as side-effect of another task.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

# Fail-closed: a protected-file gate that cannot read the path must DENY,
# not silently allow when jq is absent (observability-eye I8).
cos_require_parser block-protected-files

INPUT="$(cos_read_stdin_bounded 2)"
FILE_PATH=$(printf '%s' "$INPUT" | cos_json_field tool_input.file_path)

# Block direct edits to changes.log
if [[ "$FILE_PATH" == *"changes.log"* ]]; then
  echo "BLOCKED: Do not edit changes.log directly. Use 'make log-write TYPE=<type> MSG=\"title\" WHAT=\"impact\" FILES=\"files\"'." >&2
  exit 2
fi

# Scrumban task status changes go through `cos task-move` / `cos task-done`,
# never a hand-edit of a task file — validate-task-frontmatter.sh guards that.

# Block edits to governance/workflow files unless explicitly tasked.
# These define HOW we work — changing them as a side-effect of another task
# can silently break workflow for all future sessions.
#
# Exception: paths inside templates/.../scaffold/ are SCAFFOLD TEMPLATES, not
# runtime state. They need to be writable so coding-os itself can ship updates
# to the scaffold (e.g. adding rag-config.yaml under .coding-os/ scaffold).
# BUT: scaffold/docs/governance/ is the canonical home of governance docs
# that propagate to every future consumer project require the
# same template-update / governance / docs-update keyword guard the
# meta-repo's own governance dir uses. Other scaffold paths still pass.
# 0 when this panel's task names one of KEYWORDS — in its marker, or (since
# `cos task-start` writes the bare id) in its task file's title or labels. The
# hand-written marker Rule 25 forbids must never be the only way past a gate
# that says "open a governance task".
_task_signals() {
  local keywords="$1" agent_dir marker value name task_id root doc
  agent_dir="${COS_AGENT_DIR:-${COS_STATE_DIR:-.coding-os}/${COS_AGENT:-unknown}}"
  marker="${COS_PANEL_DIR:-$agent_dir}/.task-current"
  [ -f "$marker" ] || return 1
  value=$(cat "$marker" 2>/dev/null)
  name="${value#* }"
  printf '%s' "$name" | grep -qiE "$keywords" && return 0
  task_id=$(printf '%s' "$name" | grep -oE 'TASK-([A-Z][A-Z0-9]*-)?[0-9]+' | head -1 || true)
  [ -n "$task_id" ] || return 1
  for root in "${COS_PROJECT_ROOT:-}" "${CLAUDE_PROJECT_DIR:-}" "."; do
    [ -n "$root" ] || continue
    doc=$(ls "${root}/docs/tasks/${task_id}-"*.md 2>/dev/null | head -1 || true)
    [ -n "$doc" ] || continue
    grep -E '^(title|labels):' "$doc" 2>/dev/null | grep -qiE "$keywords" && return 0
    return 1
  done
  return 1
}

if [[ "$FILE_PATH" == *"/scaffold/docs/governance/"* ]]; then
  if _task_signals 'template-update|docs-update|docs-sync|governance|claude-md-update|agents-md-update'; then
    exit 0
  fi
  echo "BLOCKED: Edits to src/templates/_base/scaffold/docs/governance/ propagate to every future consumer project. Open a task whose title or labels include one of: template-update, docs-update, governance (cos task-create --title 'governance: ...' then cos task-start <ID>)." >&2
  exit 2
fi
if [[ "$FILE_PATH" == *"/scaffold/"* ]]; then
  exit 0
fi

# Data-driven adapter state protection: every adapter declares a state
# dir (e.g. `.claude/`, `.codex/`) — we block edits under any
# of them.  Discovery order:
#   1. src/adapters/<id>/adapter.yaml (source of truth in the meta-repo)
#   2. legacy hardcoded safety-net for meta-project setups that pre-date
#      the registry (cannot regress; this list is additive).
ADAPTER_ROOT="$(cd "$(dirname "$0")/../.." 2>/dev/null && pwd)/adapters"
ADAPTER_STATE_GLOB=""
if [ -d "$ADAPTER_ROOT" ]; then
  for adir in "$ADAPTER_ROOT"/*/; do
    [ -d "$adir" ] || continue
    aid=$(basename "$adir")
    ADAPTER_STATE_GLOB="${ADAPTER_STATE_GLOB}|.${aid}/rules/|.${aid}/hooks/|.${aid}/skills/"
  done
fi
ADAPTER_STATE_GLOB="${ADAPTER_STATE_GLOB}|.claude/rules/|.claude/hooks/|.codex/hooks/"

matched_adapter_path=0
IFS='|' read -r -a _glob_parts <<< "$ADAPTER_STATE_GLOB"
for _g in "${_glob_parts[@]}"; do
  [ -z "$_g" ] && continue
  if [[ "$FILE_PATH" == *"$_g"* ]]; then
    matched_adapter_path=1
    break
  fi
done

# Protect the src/core/ skill+rule SOURCE too: it propagates to every consumer
# via live symlinks, so it needs the same guard as its rendered .claude/ copies.
if [[ "$matched_adapter_path" -eq 1 ]] || \
   [[ "$FILE_PATH" == *".coding-os/"* ]] || \
   [[ "$FILE_PATH" == *"/CLAUDE.md" ]] || \
   [[ "$FILE_PATH" == *"/AGENTS.md" ]] || \
   [[ "$FILE_PATH" == *"src/core/skills/"* ]] || \
   [[ "$FILE_PATH" == *"src/core/rules/"* ]] || \
   [[ "$FILE_PATH" == *"infrastructure/scripts/"* ]]; then
  # Escape hatch: if the active task explicitly names governance work,
  # allow the edit. This prevents genuine docs/governance tasks from
  # being blocked by the safety net. The active task marker is session-
  # scoped and set via `cos task-start` or write-state.sh.
  # Task marker lives in the panel-private state dir (COS_PANEL_DIR per
  # ); fall back to agent dir only when cos-env.sh hasn't been
  # sourced. Falls through cleanly during the transition window.
  if _task_signals 'docs-update|docs-sync|governance|claude-md-update|agents-md-update'; then
    exit 0
  fi
  echo "BLOCKED: Governance/workflow file detected. Do not edit agent config dirs, src/core/skills/ or src/core/rules/ sources, CLAUDE.md, AGENTS.md, or infrastructure/scripts/ as a side-effect of another task. Open a task whose title or labels name the work — cos task-create --title 'governance: ...' then cos task-start <ID>." >&2
  exit 2
fi

exit 0
