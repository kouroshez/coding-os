#!/usr/bin/env bash
# PreToolUse Edit|Write — require audit artifact when exhaustive intent active.
#
# When .intent.json shows exhaustive=true, the agent MUST produce a
# compaction-resilient evidence record at docs/tasks/audits/audit-*.md.
# Without this artifact, findings live in chat and evaporate after the
# next context compaction — the very failure mode this whole layer
# exists to prevent.
#
# Fail-closed (exit 2 / BLOCK) when:
#   - intent.json present AND exhaustive=true
#   - NO docs/tasks/audits/audit-*.md exists with status:in_progress
#   - the file being edited is NOT itself the audit file / intent.json
#     / a state file under .coding-os/ / a path under /tmp
#
# Fail-open (exit 0) otherwise. One-shot override key: `audit-artifact`.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
if ! command -v cos_log_hook >/dev/null 2>&1; then cos_log_hook() { :; }; fi

cos_require_or_skip jq enforce-audit-artifact

INPUT="$(cos_read_stdin_bounded 2)"
if [[ -z "$INPUT" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
if [[ -z "$FILE_PATH" ]]; then
  exit 0
fi

# Self-edit allow-list — never block the agent from writing the very
# artifacts the hook is asking for, or from updating intent / state.
# Patterns cover both repo-relative (docs/...) and absolute (/abs/.../docs/...)
# forms the agent runtime may submit.
case "$FILE_PATH" in
  */docs/tasks/audits/*|docs/tasks/audits/*) exit 0 ;;
  */docs/_meta/audit-checklist-template.md|docs/_meta/audit-checklist-template.md) exit 0 ;;
  */.coding-os/*|.coding-os/*) exit 0 ;;
  /tmp/*|*/tmp/*) exit 0 ;;
esac

INTENT_FILE="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.intent.json"  # panel-first
[[ -f "$INTENT_FILE" ]] || INTENT_FILE="${COS_AGENT_DIR}/.intent.json"
if [[ ! -f "$INTENT_FILE" ]]; then
  # No intent recorded for this prompt — nothing to enforce.
  exit 0
fi

EXHAUSTIVE=$(jq -r '.exhaustive // false' "$INTENT_FILE" 2>/dev/null || echo "false")
if [[ "$EXHAUSTIVE" != "true" ]]; then
  exit 0
fi

# Look for any active audit artifact. Glob match — agent may use any
# slug. status:in_progress in frontmatter is the activeness signal.
# `compgen -G` expands the glob to a list of real files and returns
# nonzero if no match; `|| true` keeps `set -e` happy on empty match.
AUDIT_DIR="docs/tasks/audits"
ACTIVE=""
if [[ -d "$AUDIT_DIR" ]]; then
  AUDIT_FILES=$(compgen -G "${AUDIT_DIR}/audit-*.md" 2>/dev/null || true)
  if [[ -n "$AUDIT_FILES" ]]; then
    # Match BOTH conventions: YAML frontmatter (`^status: in_progress`,
    # template canonical) AND markdown bold (`**Status:** in_progress`,
    # historic / lenient). Mirrors session-context.sh so every audit-
    # lifecycle consumer sees the same activeness signal.
    ACTIVE=$(grep -lE "(^status:[[:space:]]+in_progress|\*\*Status:\*\*[[:space:]]+in_progress)" $AUDIT_FILES 2>/dev/null | head -1 || true)
  fi
fi

if [[ -n "$ACTIVE" ]]; then
  cos_log_hook enforce-audit-artifact ok "active=${ACTIVE}"
  exit 0
fi

# Honor one-shot override (logged in .overrides.audit.log).
if cos_one_shot_override "audit-artifact"; then
  cos_log_hook enforce-audit-artifact override-consumed
  exit 0
fi

PREDICATES=$(jq -r '.predicates | join(", ")' "$INTENT_FILE" 2>/dev/null || echo "")
MATCHED=$(jq -r '.matched_exhaustive | join(", ")' "$INTENT_FILE" 2>/dev/null || echo "")

cos_log_hook enforce-audit-artifact block "missing-audit-artifact"

cat >&2 <<MSG
BLOCKED: exhaustive intent active but no audit artifact present.

  Matched vocabulary:  ${MATCHED}
  Predicates active:   ${PREDICATES}
  Target file:         ${FILE_PATH}

Why: chat-only findings evaporate after context compaction. The whole
intent-enforcement layer exists to prevent premature 'done' on exhaustive
tasks. The completion guardian and auto-reviewer read the audit file —
not chat — as canonical evidence.

To fix (one of):

  1. Create docs/tasks/audits/audit-<slug>.md using the template:
       cp docs/_meta/audit-checklist-template.md docs/tasks/audits/audit-<slug>.md
       # then fill: audit_id, task_id, matched_exhaustive, predicates,
       # the user prompt block, and the initial Categories table.

  2. If this edit is genuinely unrelated to the exhaustive task and you
     have already documented the audit elsewhere, one-shot override:
       touch ${COS_STATE_DIR}/.audit-artifact-override

  3. If intent detection was wrong (false positive — re-read the prompt),
     correct the intent record:
       rm ${INTENT_FILE}

Full contract: docs/engineering/intent-vocabulary.md
MSG

exit 2
