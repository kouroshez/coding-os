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
if [[ "$FILE_PATH" == *"/scaffold/docs/governance/"* ]]; then
  AGENT_DIR="${COS_AGENT_DIR:-${COS_STATE_DIR:-.coding-os}/${COS_AGENT:-unknown}}"
  # Panel-aware lookup — task marker lives in $COS_PANEL_DIR
  # since the per-panel split. Falls through cleanly when COS_PANEL_DIR
  # is unset (older hook caller).
  TASK_FILE="${COS_PANEL_DIR:-$AGENT_DIR}/.task-current"
  TASK_NAME=""
  if [ -f "$TASK_FILE" ]; then
    TASK_VALUE=$(cat "$TASK_FILE" 2>/dev/null)
    # Strip ONLY the leading session-id token; keep the rest of the value.
    # `##* ` would drop everything but the LAST word, so a multi-word marker
    # (`<sid> docs-update TASK-NNN align-docs`) lost the governance keyword.
    TASK_NAME="${TASK_VALUE#* }"
  fi
  case "$TASK_NAME" in
    *template-update*|*docs-update*|*docs-sync*|*governance*|*claude-md-update*|*agents-md-update*)
      exit 0
      ;;
    *)
      echo "BLOCKED: Edits to src/templates/_base/scaffold/docs/governance/ propagate to every future consumer project. Open a task whose title includes one of: template-update, docs-update, governance. Active task: '${TASK_NAME:-none}'." >&2
      exit 2
      ;;
  esac
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
  AGENT_DIR="${COS_AGENT_DIR:-${COS_STATE_DIR:-.coding-os}/${COS_AGENT:-unknown}}"
  TASK_FILE="${COS_PANEL_DIR:-$AGENT_DIR}/.task-current"
  if [ -f "$TASK_FILE" ]; then
    TASK_VALUE=$(cat "$TASK_FILE" 2>/dev/null)
    # The task marker is "session-id value" — extract the value
    # Strip ONLY the leading session-id token; keep the rest of the value.
    # `##* ` would drop everything but the LAST word, so a multi-word marker
    # (`<sid> docs-update TASK-NNN align-docs`) lost the governance keyword.
    TASK_NAME="${TASK_VALUE#* }"
    # Allow when the task name clearly signals governance/docs work.
    case "$TASK_NAME" in
      *docs-update*|*docs-sync*|*governance*|*claude-md-update*|*agents-md-update*)
        exit 0
        ;;
    esac
    # `cos task-start` writes the bare id, so the keyword this message asks for
    # lives in the task's own title and labels — not in the marker string. Read
    # it there, or the only way past a gate that says "open a governance task"
    # is hand-writing the marker that Rule 25 forbids hand-writing.
    TASK_ID=$(printf '%s' "$TASK_NAME" | grep -oE 'TASK-([A-Z][A-Z0-9]*-)?[0-9]+' | head -1 || true)
    if [ -n "$TASK_ID" ]; then
      for _root in "${COS_PROJECT_ROOT:-}" "${CLAUDE_PROJECT_DIR:-}" "."; do
        [ -n "$_root" ] || continue
        _doc=$(ls "${_root}/docs/tasks/${TASK_ID}-"*.md 2>/dev/null | head -1 || true)
        [ -n "$_doc" ] || continue
        if grep -E '^(title|labels):' "$_doc" 2>/dev/null \
          | grep -qiE 'docs-update|docs-sync|governance|claude-md-update|agents-md-update'; then
          exit 0
        fi
        break
      done
    fi
  fi
  echo "BLOCKED: Governance/workflow file detected. Do not edit agent config dirs, src/core/skills/ or src/core/rules/ sources, CLAUDE.md, AGENTS.md, or infrastructure/scripts/ as a side-effect of another task. Open a task whose title or labels name the work — cos task-create --title 'governance: ...' then cos task-start <ID>." >&2
  exit 2
fi

exit 0
