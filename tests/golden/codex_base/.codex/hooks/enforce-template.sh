#!/usr/bin/env bash
# PreToolUse hook: Enforce template usage for structured doc creation.
#
# Four classes of markdown files have canonical creation flows:
#   docs/tasks/TASK-*.md          → `cos task-create --title "..." --swimlane <lane> --kind <kind>`
#   docs/architecture/adr/ADR-*.md → copy docs/governance/_templates/adr-template.md
#   docs/prd/NN-*.md              → `cos setup --mode ...`
#   docs/insights/*.md             → cos_learn_narrative MCP tool
#
# This hook BLOCKS raw Write on those paths and redirects to the right
# tool. It runs only on Write (not Edit) and only when the target does
# not already exist — so fixing an existing task file is still free.
#
# Escape hatch: set $COS_AGENT_DIR/.template-override (any content) to
# allow a one-time raw write. Useful for scaffold regeneration.
set -euo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
INPUT="$(cos_read_stdin_bounded 2)"
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")

# Only enforce on Write (true creation). Edit implies the file exists.
if [[ "$TOOL" != "Write" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
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

COS_STATE_DIR="${COS_STATE_DIR:-.coding-os}"

# Formula-agents that write docs (architect/documenter) produce
# structured output by design — skip template gate when a role dispatch is active.
ACTIVE_FORMULA_FILE="${COS_PANEL_DIR:-$COS_AGENT_DIR}/.active-formula"  # panel-first: written to + cleared from the panel dir
if [[ -f "$ACTIVE_FORMULA_FILE" ]]; then
  ACTIVE_FORMULA=$(cat "$ACTIVE_FORMULA_FILE" 2>/dev/null || echo "")
  # architect creates ADRs; documenter creates task/PRD/breakthrough docs.
  # Both operate within structured output contracts — no template re-enforcement needed.
  if [[ -n "$ACTIVE_FORMULA" ]]; then
    exit 0
  fi
fi

# One-shot escape hatch for tooling (scaffold writers, migration scripts).
# Unified registry preferred; legacy $COS_AGENT_DIR/.template-override still honoured.
if cos_one_shot_override template 2>/dev/null; then
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
  TEMPLATE="$DOCS_ROOT/governance/_templates/adr-template.md"
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
# docs/prd/NN-*.md — the cos setup command owns this bootstrap.
if [[ "$FILE_PATH" =~ docs/prd/[0-9]+.*\.md$ ]]; then
  echo "BLOCKED: PRD files should be bootstrapped via \`cos setup\`." >&2
  echo "  File: $FILE_PATH" >&2
  echo "  Use one of:" >&2
  echo "    cos setup --mode interactive                    # 4-question wizard" >&2
  echo "    cos setup --mode import-prd --source <path>     # split an existing PRD" >&2
  echo "  The classifier routes sections to the right numbered file." >&2
  echo "  (Override for one write: touch $COS_AGENT_DIR/.template-override)" >&2
  exit 2
fi

# ── Insight files ────────────────────────────────────────────────────
# docs/insights/*.md — auto-filed by cos_learn_narrative. Only the
# scaffold 00-index.md is hand-written.
if [[ "$FILE_PATH" == *docs/insights/*.md ]]; then
  if [[ "$BASENAME" == "00-index.md" ]]; then
    exit 0
  fi
  echo "BLOCKED: insight files are filed back by the MCP tool." >&2
  echo "  File: $FILE_PATH" >&2
  echo "  Call cos_learn_narrative with task_id, what_failed, what_worked, key_insight." >&2
  echo "  The tool writes the markdown + the outcome_history DB row atomically." >&2
  echo "  (Override for one write: touch $COS_AGENT_DIR/.template-override)" >&2
  exit 2
fi

# Freeform .md paths (playbooks, engineering rules, ad-hoc notes) are allowed,
# but a NEW docs/*.md should carry the SSOT front-matter header. WARN (never
# block) at write time so the author sees the doc-cheat-sheet contract early —
# the CI `docs-lint --changed` strict step is the hard gate. TASK-127.
case "$FILE_PATH" in
  */docs/tasks/*) ;;  # task files have their own template flow above
  *docs/*.md)
    CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // empty' 2>/dev/null || echo "")
    FIRST_LINE=$(printf '%s\n' "$CONTENT" | head -1)
    if ! printf '%s' "$FIRST_LINE" | grep -qE '^<!-- domain:[A-Z_]+ \| layer:[a-z]+ \| ssot:(true|ref|false)'; then
      echo "warning: new doc $FILE_PATH is missing the SSOT front-matter header" >&2
      echo "  line 1 should be: <!-- domain:X | layer:Y | ssot:true|ref|false | updated:YYYY-MM-DD -->" >&2
      echo "  see docs/governance/docs-system.md (doc-cheat-sheet). Advisory — not blocking." >&2
    fi
    ;;
esac
exit 0
