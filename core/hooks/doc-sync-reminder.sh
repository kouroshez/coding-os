#!/usr/bin/env bash
# PostToolUse hook: After Write/Edit on code, remind about companion docs.
#
# Soft nudge — never blocks. Prints the docs that likely describe the
# changed code so the agent remembers to update them in the same session.
# Addresses the "code shipped but docs went stale" drift that turns the
# agent workflow into two sources of truth.
#
# Mapping order:
#   1. $COS_STATE_DIR/doc-map.yaml   (optional, project-level explicit)
#   2. Built-in heuristics below     (matches common coding-os layout)
#
# Silent no-op when:
#   - The tool is not Write/Edit
#   - The changed file is a test, migration, cache, or internal state dir
#   - No mapping rule matches
set -euo pipefail

INPUT=$(cat)
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')
if [[ "$TOOL" != "Write" && "$TOOL" != "Edit" ]]; then
  exit 0
fi

FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
[[ -z "$FILE_PATH" ]] && exit 0

# Only nudge on code files.
case "$FILE_PATH" in
  *.py|*.ts|*.tsx|*.js|*.jsx|*.go|*.rb|*.rs|*.sh) ;;
  *) exit 0 ;;
esac

# Skip tests, fixtures, caches, vendored, and internal state.
# Patterns are strict (filename-level, not path-level) to avoid false
# matches against temp paths like /var/folders/.../test_cli_py0/cli/main.py.
BASENAME=$(basename "$FILE_PATH")
case "$BASENAME" in
  test_*|*_test.*|conftest.py) exit 0 ;;
esac
case "$FILE_PATH" in
  */tests/*|*/__pycache__/*|*/migrations/*|*/node_modules/*) exit 0 ;;
  */.venv/*|*/.coding-os/*|*/.claude/*|*/.codex/*) exit 0 ;;
esac

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true
COS_STATE_DIR="${COS_STATE_DIR:-.coding-os}"

RELATED=()

# ── Built-in heuristics ──────────────────────────────────────────────
# Keep patterns specific enough to avoid false positives. Each branch
# appends one or more doc references. Order doesn't matter — first match
# only, to keep output focused.
case "$FILE_PATH" in
  *cli/*.py)
    RELATED+=(
      "README.md (§ Command Index)"
      "docs/features.md (§ Command Catalog)"
      "docs/getting-started.md (§ Quick Start)"
    )
    ;;
  *core/hooks/*.sh)
    RELATED+=(
      "docs/engineering/hooks-reference.md (catalog of all hooks)"
      "docs/features.md (§ Hook System)"
      "docs/architecture.md (§ Hook Execution Flow)"
      "core/hooks/registry.yaml (SSOT — register new hooks here)"
    )
    ;;
  *core/hooks/enforce-template.sh)
    RELATED+=(
      "docs/engineering/template-enforcement.md (canonical reference)"
    )
    ;;
  *core/hooks/enforce-skill.sh|*core/rules/skill-enforcement.md)
    RELATED+=(
      "docs/engineering/skill-architecture.md (fundamentals + specialization)"
    )
    ;;
  *core/thinking_os/server.py|*core/thinking_os/tools/*.py)
    RELATED+=(
      "docs/architecture.md (§ MCP Tools)"
      "docs/engineering/mcp-error-envelope.md (ok/fail envelope contract)"
      "docs/features.md (§ MCP Tools)"
      "CLAUDE.md (§ Critical Rules — MCP tool names)"
    )
    ;;
  *core/skills/backend-fundamentals/*|*core/skills/frontend-fundamentals/*)
    RELATED+=(
      "docs/engineering/skill-architecture.md (base + specialization layering)"
    )
    ;;
  *core/thinking_os/db.py)
    RELATED+=(
      "docs/architecture.md (§ Database Schema)"
      "docs/features.md (§ Database Schema)"
    )
    ;;
  *core/thinking_os/*.py)
    RELATED+=(
      "docs/architecture.md (§ Three-Layer Retrieval)"
      "docs/features.md (§ Self-Learning Pipeline)"
    )
    ;;
  *templates/*/stack.yaml|*templates/*/*.yaml)
    RELATED+=(
      "docs/features.md (§ Skills — stack-scoped)"
      "README.md (§ Adding a new stack)"
    )
    ;;
  *adapters/*/adapter.yaml|*adapters/*/install.sh)
    RELATED+=(
      "docs/architecture.md (§ Adapters / Portability)"
      "docs/features.md (§ Per-Project Structure)"
    )
    ;;
  *backend/*.py)
    RELATED+=(
      "docs/engineering/backend-rules.md"
      "docs/playbooks/backend-api.md"
    )
    ;;
  *frontend/*.ts|*frontend/*.tsx|*frontend/*.jsx)
    RELATED+=(
      "docs/engineering/frontend-rules.md"
      "docs/playbooks/frontend-ui.md"
    )
    ;;
esac

# ── Optional project-level overrides ─────────────────────────────────
# $COS_STATE_DIR/doc-map.yaml lets a project add extra mappings without
# touching the hook. Minimal format — no full YAML parse to keep the
# dependency surface small:
#
#   # one rule per line:
#   match_substring=>doc1,doc2
#
# Example:
#   app/services/=>docs/engineering/services.md,docs/playbooks/service-layer.md
DOC_MAP="$COS_STATE_DIR/doc-map.yaml"
if [[ -f "$DOC_MAP" ]]; then
  while IFS= read -r line; do
    # Skip comments and blanks.
    [[ -z "${line// }" ]] && continue
    [[ "$line" == \#* ]] && continue
    # Expect: <substring>=><doc1>,<doc2>
    [[ "$line" != *"=>"* ]] && continue
    needle="${line%%=>*}"
    docs="${line##*=>}"
    if [[ "$FILE_PATH" == *"$needle"* ]]; then
      IFS=',' read -ra MORE <<< "$docs"
      for d in "${MORE[@]}"; do
        d="${d# }"; d="${d% }"
        [[ -n "$d" ]] && RELATED+=("$d")
      done
    fi
  done < "$DOC_MAP"
fi

if [[ ${#RELATED[@]} -eq 0 ]]; then
  exit 0
fi

# Print once, concise. Do NOT block.
echo ""
echo "  📘 [doc-sync] Code changed — keep these docs in sync in this session:"
for d in "${RELATED[@]}"; do
  echo "     → $d"
done
echo "     (Reminder only. See docs/features.md for the full doc map.)"

exit 0
