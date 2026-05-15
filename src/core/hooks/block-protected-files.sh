#!/usr/bin/env bash
# PreToolUse hook: Block direct edits to protected files.
# Protected:
#   - changes.log (use make log-write)
#   - tasks.md status lines (use make task-done/task-start)
#   - Governance files: agent rules/, hooks/, CLAUDE.md, AGENTS.md,
#     infrastructure/scripts/ — never edit as side-effect of another task.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

INPUT="$(cos_read_stdin_bounded 2)"
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
OLD_STRING=$(echo "$INPUT" | jq -r '.tool_input.old_string // empty' 2>/dev/null || echo "")

# Block direct edits to changes.log
if [[ "$FILE_PATH" == *"changes.log"* ]]; then
  echo "BLOCKED: Do not edit changes.log directly. Use 'make log-write TYPE=<type> MSG=\"title\" WHAT=\"impact\" FILES=\"files\"' or 'make task-done'." >&2
  exit 2
fi

# Block direct status changes in tasks.md (checkbox modifications)
if [[ "$FILE_PATH" == *"docs/tasks.md"* ]]; then
  if echo "$OLD_STRING" | grep -qE '^\- \[[ x/]\]'; then
    echo "BLOCKED: Do not change task status directly in tasks.md. Use 'make task-start TASK=<num>', 'make task-done TASK=<num> TYPE=<type> MSG=\"title\" WHAT=\"impact\" FILES=\"files\"', or 'make task-block TASK=<num> REASON=\"why\"'." >&2
    exit 2
  fi
fi

# Block edits to governance/workflow files unless explicitly tasked.
# These define HOW we work — changing them as a side-effect of another task
# can silently break workflow for all future sessions.
#
# Exception: paths inside templates/.../scaffold/ are SCAFFOLD TEMPLATES, not
# runtime state. They need to be writable so coding-os itself can ship updates
# to the scaffold (e.g. adding rag-config.yaml under .coding-os/ scaffold).
# BUT: scaffold/docs/governance/ is the canonical home of governance docs
# that propagate to every future consumer project — TASK-162 requires the
# same template-update / governance / docs-update keyword guard the
# meta-repo's own governance dir uses. Other scaffold paths still pass.
if [[ "$FILE_PATH" == *"/scaffold/docs/governance/"* ]]; then
  AGENT_DIR="${COS_AGENT_DIR:-${COS_STATE_DIR:-.coding-os}/${COS_AGENT:-unknown}}"
  TASK_FILE="$AGENT_DIR/.task-current"
  TASK_NAME=""
  if [ -f "$TASK_FILE" ]; then
    TASK_VALUE=$(cat "$TASK_FILE" 2>/dev/null)
    TASK_NAME="${TASK_VALUE##* }"
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
# dir (e.g. `.claude/`, `.codex/`, `.cursor/`) — we block edits under any
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
ADAPTER_STATE_GLOB="${ADAPTER_STATE_GLOB}|.claude/rules/|.claude/hooks/|.codex/hooks/|.cursor/hooks/"

matched_adapter_path=0
IFS='|' read -r -a _glob_parts <<< "$ADAPTER_STATE_GLOB"
for _g in "${_glob_parts[@]}"; do
  [ -z "$_g" ] && continue
  if [[ "$FILE_PATH" == *"$_g"* ]]; then
    matched_adapter_path=1
    break
  fi
done

if [[ "$matched_adapter_path" -eq 1 ]] || \
   [[ "$FILE_PATH" == *".coding-os/"* ]] || \
   [[ "$FILE_PATH" == *"/CLAUDE.md" ]] || \
   [[ "$FILE_PATH" == *"/AGENTS.md" ]] || \
   [[ "$FILE_PATH" == *"infrastructure/scripts/"* ]]; then
  # Escape hatch: if the active task explicitly names governance work,
  # allow the edit. This prevents genuine docs/governance tasks from
  # being blocked by the safety net. The active task marker is session-
  # scoped and set via `make task-start` or write-state.sh.
  # Task marker lives in the agent-private state dir (COS_AGENT_DIR); when
  # cos-env.sh hasn't been sourced we fall back to the shared root.
  AGENT_DIR="${COS_AGENT_DIR:-${COS_STATE_DIR:-.coding-os}/${COS_AGENT:-unknown}}"
  TASK_FILE="$AGENT_DIR/.task-current"
  if [ -f "$TASK_FILE" ]; then
    TASK_VALUE=$(cat "$TASK_FILE" 2>/dev/null)
    # The task marker is "session-id value" — extract the value
    TASK_NAME="${TASK_VALUE##* }"
    # Allow when the task name clearly signals governance/docs work.
    case "$TASK_NAME" in
      *docs-update*|*docs-sync*|*governance*|*claude-md-update*|*agents-md-update*)
        exit 0
        ;;
    esac
  fi
  echo "BLOCKED: Governance/workflow file detected. Do not edit agent config dirs, CLAUDE.md, AGENTS.md, or infrastructure/scripts/ as a side-effect of another task. Create a dedicated task for governance changes, e.g. write-state.sh $AGENT_DIR/.task-current 'docs-update-...'" >&2
  exit 2
fi

exit 0
