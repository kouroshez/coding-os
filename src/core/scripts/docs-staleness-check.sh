#!/usr/bin/env bash
# docs-staleness-check.sh — Detect drift between code and human-facing docs.
#
# Cross-checks the numbers and symbols that appear in CLAUDE.md against their
# source of truth in the codebase:
#
#   - MCP tool count: distinct @mcp.tool(name="cos_...") registrations across
#     src/core/thinking_os/ → should match "XX cos_* tools" in CLAUDE.md.
#
#   - Schema version: highest version in MIGRATIONS (_db_migrations.py) →
#     should match "Database Schema (vXX)" where a doc claims one.
#
#   - Table count: len(_TABLES) in database.py.
#
#   - Stale legacy strings: "nako_*" tool names that should have become "cos_*".
#
# Every measured number carries a sanity floor. A floor trip means the symbol
# moved and the check is reading air, which is a broken instrument rather than
# a docs error — it aborts loudly instead of reporting a green zero.
#
# Exit: 0 = all consistent, 1 = staleness found (lists everything).
#
# Usage:
#   bash src/core/scripts/docs-staleness-check.sh
#   bash src/core/scripts/docs-staleness-check.sh --quiet
#
# Wired into `make docs-lint` (runs after the markdown front-matter checks).

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/_lib.sh"

# Repo root is three levels up: scripts → core → src → <root>. The src-layout
# migration left COS_ROOT one level short, so the code paths resolved by luck
# while CLAUDE.md (at the real root) silently never matched.
COS_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
QUIET=0

for arg in "$@"; do
  case "$arg" in
    --quiet) QUIET=1 ;;
    --help|-h)
      echo "Usage: $0 [--quiet]"
      echo "Cross-check CLAUDE.md against the code it cites."
      exit 0
      ;;
  esac
done

ERRORS=0
WARNINGS=0
CHECKED=0

note_error() {
  ERRORS=$((ERRORS + 1))
  echo "  ERROR: $1" >&2
}

note_warning() {
  WARNINGS=$((WARNINGS + 1))
  [ "$QUIET" -eq 0 ] && echo "  WARN: $1" >&2
}

# ── Compute expected values from the codebase ───────────────────────────────

THINKING_OS_DIR="$COS_ROOT/src/core/thinking_os"
MIGRATIONS_PY="$THINKING_OS_DIR/_db_migrations.py"
DB_PY="$THINKING_OS_DIR/database.py"
CLAUDE_MD="$COS_ROOT/CLAUDE.md"

# Floors, not equalities. Each number below is read out of a symbol that has
# already moved once — tools left server.py, MIGRATIONS left database.py — and
# a moved symbol reads as 0 or 1, which every comparison below then "passes".
# A floor turns that silence into an abort while staying far enough under the
# live values that ordinary growth never trips it.
MIN_TOOL_COUNT=50
MIN_SCHEMA_VERSION=40
MIN_TABLE_COUNT=15

[ -d "$THINKING_OS_DIR" ] || err "thinking_os package not found at $THINKING_OS_DIR"
[ -f "$MIGRATIONS_PY" ] || err "_db_migrations.py not found at $MIGRATIONS_PY"
[ -f "$DB_PY" ] || err "database.py not found at $DB_PY"

enforce_floor() {
  local label="$1" actual="$2" floor="$3" source_path="$4"
  if [ "${actual:-0}" -lt "$floor" ]; then
    err "$label read as '${actual:-<empty>}', below the sanity floor of $floor — this check is measuring nothing. Confirm $source_path still holds it, then update the extractor here."
  fi
}

# Registered tools are @mcp.tool(name="cos_...") decorators spread across
# _tools_*.py and tools/_cognition_*.py; server.py holds exactly one. Read via
# the AST so a decorator quoted inside a docstring and a stub registered under
# a computed name cannot inflate the count.
TOOL_COUNT=$(COS_THINKING_OS_DIR="$THINKING_OS_DIR" python3 - <<'PY'
import ast
import os
import pathlib

MCP_DECORATOR_ATTRIBUTE = "tool"
TOOL_NAME_PREFIX = "cos_"


def literal_tool_name(decorator):
    if not isinstance(decorator, ast.Call):
        return None
    target = decorator.func
    if not isinstance(target, ast.Attribute) or target.attr != MCP_DECORATOR_ATTRIBUTE:
        return None
    for keyword in decorator.keywords:
        if keyword.arg != "name" or not isinstance(keyword.value, ast.Constant):
            continue
        value = keyword.value.value
        if isinstance(value, str) and value.startswith(TOOL_NAME_PREFIX):
            return value
    return None


def decorators(tree):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield from node.decorator_list


def source_files(root):
    return (path for path in sorted(root.rglob("*.py")) if "tests" not in path.parts)


root = pathlib.Path(os.environ["COS_THINKING_OS_DIR"])
names = {
    name
    for path in source_files(root)
    for decorator in decorators(ast.parse(path.read_text(encoding="utf-8")))
    if (name := literal_tool_name(decorator))
}
print(len(names))
PY
)
CHECKED=$((CHECKED + 1))

# Highest version in the MIGRATIONS list — the schema version a fresh DB lands on.
SCHEMA_VERSION=$(COS_MIGRATIONS_PY="$MIGRATIONS_PY" python3 - <<'PY'
import os
import re

source = open(os.environ["COS_MIGRATIONS_PY"], encoding="utf-8").read()
match = re.search(r"^MIGRATIONS[^=]*=\s*\[(.+?)^\]", source, re.DOTALL | re.MULTILINE)
versions = re.findall(r"^\s*\(\s*(\d+)\s*,", match.group(1), re.MULTILINE) if match else []
print(max(int(version) for version in versions) if versions else 0)
PY
)
CHECKED=$((CHECKED + 1))

# Count tables in the _TABLES list
TABLE_COUNT=$(COS_DB_PY="$DB_PY" python3 - <<'PY'
import os
import re

source = open(os.environ["COS_DB_PY"], encoding="utf-8").read()
match = re.search(r"_TABLES\s*=\s*\[(.*?)\]", source, re.DOTALL)
print(len(re.findall(r'"([a-z_0-9]+)"', match.group(1))) if match else 0)
PY
)
CHECKED=$((CHECKED + 1))

info "Source of truth:"
info "  MCP tools registered (@mcp.tool name=\"cos_*\"): $TOOL_COUNT"
info "  Schema version (highest in MIGRATIONS):        $SCHEMA_VERSION"
info "  Tables in _TABLES list:                        $TABLE_COUNT"

enforce_floor "MCP tool count" "$TOOL_COUNT" "$MIN_TOOL_COUNT" "$THINKING_OS_DIR"
enforce_floor "Schema version" "$SCHEMA_VERSION" "$MIN_SCHEMA_VERSION" "$MIGRATIONS_PY"
enforce_floor "Table count" "$TABLE_COUNT" "$MIN_TABLE_COUNT" "$DB_PY"

# ── Cross-check CLAUDE.md ───────────────────────────────────────────────────

if [ -f "$CLAUDE_MD" ]; then
  CHECKED=$((CHECKED + 1))

  # Look for an "XX cos_* tools" claim. The phrase is OPTIONAL — CLAUDE.md /
  # AGENTS.md deliberately delegate the live count to mcp-tool-inventory.md, so
  # absence is the intended state. Only a present-but-wrong number is an error.
  DOC_TOOL_COUNT=$(grep -oE '[0-9]+ cos_\* tools' "$CLAUDE_MD" | head -1 | grep -oE '^[0-9]+')
  if [ -n "${DOC_TOOL_COUNT:-}" ] && [ "$DOC_TOOL_COUNT" != "$TOOL_COUNT" ]; then
    note_error "CLAUDE.md claims '$DOC_TOOL_COUNT cos_* tools' but thinking_os registers $TOOL_COUNT"
  fi

  # Stale legacy references
  if grep -q '\bnako_' "$CLAUDE_MD"; then
    note_error "CLAUDE.md contains legacy 'nako_*' references — should be 'cos_*'"
  fi
  if grep -q 'Database Schema (v[0-9]' "$CLAUDE_MD"; then
    CLAUDE_SCHEMA=$(grep -oE 'Database Schema \(v[0-9]+\)' "$CLAUDE_MD" | head -1 | grep -oE '[0-9]+')
    if [ "$CLAUDE_SCHEMA" != "$SCHEMA_VERSION" ]; then
      note_error "CLAUDE.md claims schema v$CLAUDE_SCHEMA but MIGRATIONS tops out at v$SCHEMA_VERSION"
    fi
  fi
fi

# Note: the old docs/architecture.md cross-check was removed — that file no
# longer exists (architecture is a directory now) and no doc currently carries
# the "MCP Tools (NN)" / "Database Schema (vN)" headings, so the block only ever
# evaluated a missing-file no-op. CLAUDE.md remains the live cross-check above.
#
# The tool-count and schema-version comparisons are conditional on CLAUDE.md
# carrying the phrase, and it currently carries neither; the table count has no
# doc claiming it at all. So on a clean tree the floors are the only thing this
# check actually asserts — they prove the numbers are real, not that a doc
# agrees with them. Delete a floor only by replacing it with a doc comparison.

# ── Summary ─────────────────────────────────────────────────────────────────

echo ""
if [ "$ERRORS" -eq 0 ]; then
  ok "docs-staleness-check passed: $CHECKED source(s) checked, 0 errors, $WARNINGS warning(s)"
  exit 0
else
  err "docs-staleness-check failed: $ERRORS error(s), $WARNINGS warning(s). Update the affected docs."
fi
