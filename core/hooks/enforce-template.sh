#!/usr/bin/env bash
# PreToolUse hook: Enforce template usage for structured doc creation.
#
# Four classes of markdown files have canonical creation flows:
#   docs/tasks/TASK-*.md          → `make task-create NUM=N TITLE="..."`
#   docs/architecture/adr/ADR-*.md → copy docs/governance/templates/adr-template.md
#   docs/PRD/NN-*.md              → `cos setup --mode ...`
#   docs/breakthroughs/*.md        → cos_learn_narrative MCP tool
#
# This hook BLOCKS raw Write on those paths and redirects to the right
# tool. It runs only on Write (not Edit) and only when the target does
# not already exist — so fixing an existing task file is still free.
#
# Escape hatch: set $COS_AGENT_DIR/.template-override (any content) to
# allow a one-time raw write. Useful for scaffold regeneration.
set -euo pipefail

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')

# Only enforce on Write (true creation). Edit implies the file exists.
if [[ "$TOOL" != "Write" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
[[ -z "$FILE_PATH" ]] && exit 0

# Not a markdown file → nothing to enforce here.
[[ "$FILE_PATH" != *.md ]] && exit 0

# If the target file already exists, treat as edit → allow.
[[ -f "$FILE_PATH" ]] && exit 0

# Skip obvious internal / test paths.
case "$FILE_PATH" in
  */.coding-os/*|*/.claude/*|*/.codex/*|*/tests/*|*/golden/*|*/node_modules/*|*/.git/*)
    exit 0 ;;
esac

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
COS_STATE_DIR="${COS_STATE_DIR:-.coding-os}"

# Phase M: formula-agents that write docs (F3/F4) produce structured output by
# design — skip template gate when a persona's formula dispatch is active.
ACTIVE_FORMULA_FILE="${COS_AGENT_DIR}/.active-formula"
if [[ -f "$ACTIVE_FORMULA_FILE" ]]; then
  ACTIVE_FORMULA=$(cat "$ACTIVE_FORMULA_FILE" 2>/dev/null || echo "")
  # F3 (Architect) creates ADRs; F4 (Document) creates task/PRD/breakthrough docs.
  # Both operate within structured output contracts — no template re-enforcement needed.
  if [[ -n "$ACTIVE_FORMULA" ]]; then
    exit 0
  fi
fi

# One-shot escape hatch for tooling (scaffold writers, migration scripts).
if [[ -f "$COS_AGENT_DIR/.template-override" ]]; then
  rm -f "$COS_AGENT_DIR/.template-override"
  exit 0
fi

BASENAME=$(basename "$FILE_PATH")

# ── Task detail files ────────────────────────────────────────────────
# docs/tasks/TASK-###-slug.md  — must go through the Scrumban CLI so the
# lean L-format template is applied and the task is synced to the DB.
if [[ "$FILE_PATH" == *docs/tasks/TASK-*.md ]]; then
  echo "BLOCKED: do not hand-write task files." >&2
  echo "  File:     $FILE_PATH" >&2
  echo "  Use the Scrumban CLI instead:" >&2
  echo "    cos task-create --title \"...\" --swimlane <domain> --kind <type>" >&2
  echo "  This applies the lean L-format template, validates frontmatter," >&2
  echo "  and syncs the task into the project DB in one call." >&2
  echo "  (Override for one write: touch $COS_AGENT_DIR/.template-override)" >&2
  exit 2
fi

# ── ADR files ────────────────────────────────────────────────────────
# docs/architecture/adr/ADR-###-slug.md — if the project ships an ADR
# template, require copying it; otherwise print the expected structure.
if [[ "$FILE_PATH" == *docs/architecture/adr/ADR-*.md ]]; then
  # Walk up from the ADR path to find docs/
  DOCS_ROOT="$(dirname "$(dirname "$(dirname "$FILE_PATH")")")"
  TEMPLATE="$DOCS_ROOT/governance/templates/adr-template.md"
  if [[ -f "$TEMPLATE" ]]; then
    echo "BLOCKED: use the ADR template." >&2
    echo "  Template: $TEMPLATE" >&2
    echo "  Copy its structure into $FILE_PATH, keep H2 sections intact." >&2
    echo "  (Override for one write: touch $COS_AGENT_DIR/.template-override)" >&2
    exit 2
  fi
  # No template file yet → soft reminder, allow write.
  echo "[template] Creating an ADR without a template file." >&2
  echo "  Required H2 sections: ## Status · ## Context · ## Decision · ## Consequences · ## Alternatives considered" >&2
  echo "  Consider adding $TEMPLATE for future ADRs." >&2
  exit 0
fi

# ── PRD files ────────────────────────────────────────────────────────
# docs/PRD/NN-*.md — the cos setup command owns this bootstrap.
if [[ "$FILE_PATH" =~ docs/PRD/[0-9]+.*\.md$ ]]; then
  echo "BLOCKED: PRD files should be bootstrapped via \`cos setup\`." >&2
  echo "  File: $FILE_PATH" >&2
  echo "  Use one of:" >&2
  echo "    cos setup --mode interactive                    # 4-question wizard" >&2
  echo "    cos setup --mode import-prd --source <path>     # split an existing PRD" >&2
  echo "  The classifier routes sections to the right numbered file." >&2
  echo "  (Override for one write: touch $COS_AGENT_DIR/.template-override)" >&2
  exit 2
fi

# ── Breakthrough files ───────────────────────────────────────────────
# docs/breakthroughs/*.md — auto-filed by cos_learn_narrative. Only the
# scaffold 00-index.md is hand-written.
if [[ "$FILE_PATH" == *docs/breakthroughs/*.md ]]; then
  if [[ "$BASENAME" == "00-index.md" ]]; then
    exit 0
  fi
  echo "BLOCKED: breakthrough files are filed back by the MCP tool." >&2
  echo "  File: $FILE_PATH" >&2
  echo "  Call cos_learn_narrative with task_id, what_failed, what_worked, key_insight." >&2
  echo "  The tool writes the markdown + the outcome_history DB row atomically." >&2
  echo "  (Override for one write: touch $COS_AGENT_DIR/.template-override)" >&2
  exit 2
fi

# Freeform .md paths (playbooks, engineering rules, ad-hoc notes) are allowed.
exit 0
