#!/usr/bin/env bash
# inject-subagent-task.sh — SubagentStart: hand a subagent the parent session's
# task. A subagent never sees the UserPromptSubmit pulse, yet its tool calls run
# the same enforcement hooks against the same panel, so it must know which task
# its edits belong to. Contract: docs/engineering/task-mode-matrix.md.
# Fail-open: a missing dep or unreadable state emits nothing (SubagentStart
# cannot block creation anyway).
set -uo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null \
  || source "$(dirname "$0")/../../../core/hooks/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi
command -v jq >/dev/null 2>&1 || exit 0

INPUT="$(cos_read_stdin_bounded 2 2>/dev/null || true)"
cos_panel_upgrade_from_payload "$INPUT" >/dev/null 2>&1 || true
source "$(dirname "$0")/check-state.sh" 2>/dev/null \
  || source "$(dirname "$0")/../../../core/hooks/check-state.sh" 2>/dev/null || exit 0
type cos_active_task >/dev/null 2>&1 || exit 0

RULES="Do not write .doc-anchor, .task-current or .thinking_os-gate markers and do not record a CLEAR 1 gate: if an edit is blocked, stop and report back to the parent instead of working around it."
if cos_active_task; then
  TASK_FILE=$(ls "$(_cos_project_root)"/docs/tasks/"$ACTIVE_TASK_ID"-*.md 2>/dev/null | head -1 || true)
  # The frontmatter title is a JSON-style quoted string (\u escapes), so jq decodes it.
  TITLE=$(sed -nE 's/^title:[[:space:]]*(".*")[[:space:]]*$/\1/p' "$TASK_FILE" 2>/dev/null | head -1 | jq -r . 2>/dev/null || true)
  READ_FIRST=$(awk '/^## Read First/{on=1; next} /^## /{on=0} on && /^- /{sub(/^- /, ""); printf "%s%s", sep, $0; sep="; "}' "$TASK_FILE" 2>/dev/null || true)
  CONTEXT="[coding-os task] The parent session works on ${ACTIVE_TASK_ID} (${ACTIVE_TASK_STATUS}): ${TITLE:-see cos task-show ${ACTIVE_TASK_ID}}. Read First: ${READ_FIRST:-none}. Any edit you make is part of ${ACTIVE_TASK_ID}; stay inside its scope. ${RULES}"
else
  CONTEXT="[coding-os task] The parent session has no in_progress task, so code edits are blocked. Research and report back; leave edits to the parent. ${RULES}"
fi

jq -cn --arg ctx "$CONTEXT" '{hookSpecificOutput: {hookEventName: "SubagentStart", additionalContext: $ctx}}'
cos_log_hook inject-subagent-task ok "task=${ACTIVE_TASK_ID:-none}" || true
exit 0
