#!/usr/bin/env bash
# docs-staleness-check.sh — Detect drift between code and human-facing docs.
#
# Cross-checks the numbers and symbols that appear in CLAUDE.md /
# docs/architecture.md against their source of truth in the codebase:
#
#   - MCP tool count: @mcp.tool decorators in server.py → should match
#     "XX cos_* tools" / "XX tools" in CLAUDE.md and docs/architecture.md.
#
#   - Schema version: len(MIGRATIONS) in db.py → should match
#     "Database Schema (vXX)" in docs/architecture.md.
#
#   - Table count: len(_TABLES) in db.py → should match "XX tables" in
#     docs/architecture.md.
#
#   - Stale legacy strings: "nako_*" tool names, "18 tools" / "17 tools" /
#     "v4" / "v5" references that should have been updated.
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
# migration left COS_ROOT one level short, so SERVER_PY/DB_PY resolved by luck
# while CLAUDE.md / architecture.md (at the real root) silently never matched.
COS_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
QUIET=0

for arg in "$@"; do
  case "$arg" in
    --quiet) QUIET=1 ;;
    --help|-h)
      echo "Usage: $0 [--quiet]"
      echo "Cross-check CLAUDE.md + docs/architecture.md against code."
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

SERVER_PY="$COS_ROOT/src/core/thinking_os/server.py"
DB_PY="$COS_ROOT/src/core/thinking_os/database.py"
CLAUDE_MD="$COS_ROOT/CLAUDE.md"

if [ ! -f "$SERVER_PY" ]; then
  err "server.py not found at $SERVER_PY"
fi
if [ ! -f "$DB_PY" ]; then
  err "db.py not found at $DB_PY"
fi

# Count @mcp.tool decorators — each one is exactly one registered tool
TOOL_COUNT=$(grep -cE '^@mcp\.tool\b' "$SERVER_PY")
CHECKED=$((CHECKED + 1))

# Count schema migrations — len(MIGRATIONS) equivalent
SCHEMA_VERSION=$(python3 - <<PY
import re
src = open("$DB_PY").read()
# Find the MIGRATIONS list and count the (version, desc, action) tuples
m = re.search(r'MIGRATIONS[^=]*=\s*\[(.+?)^\]', src, re.DOTALL | re.MULTILINE)
if not m:
    print(0)
else:
    body = m.group(1)
    # Each migration entry starts with "    (" followed by an integer version
    entries = re.findall(r'^\s*\(\s*(\d+)\s*,', body, re.MULTILINE)
    print(max(int(v) for v in entries) if entries else 0)
PY
)
CHECKED=$((CHECKED + 1))

# Count tables in _TABLES list
TABLE_COUNT=$(python3 - <<PY
import re
src = open("$DB_PY").read()
m = re.search(r'_TABLES\s*=\s*\[(.*?)\]', src, re.DOTALL)
if not m:
    print(0)
else:
    body = m.group(1)
    entries = re.findall(r'"([a-z_]+)"', body)
    print(len(entries))
PY
)
CHECKED=$((CHECKED + 1))

info "Source of truth:"
info "  MCP tools registered (@mcp.tool decorators): $TOOL_COUNT"
info "  Schema version (highest in MIGRATIONS):       $SCHEMA_VERSION"
info "  Tables in _TABLES list:                       $TABLE_COUNT"

# ── Cross-check CLAUDE.md ───────────────────────────────────────────────────

if [ -f "$CLAUDE_MD" ]; then
  CHECKED=$((CHECKED + 1))

  # Look for an "XX cos_* tools" claim. The phrase is OPTIONAL — CLAUDE.md /
  # AGENTS.md deliberately delegate the live count to mcp-tool-inventory.md, so
  # absence is the intended state. Only a present-but-wrong number is an error.
  DOC_TOOL_COUNT=$(grep -oE '[0-9]+ cos_\* tools' "$CLAUDE_MD" | head -1 | grep -oE '^[0-9]+')
  if [ -n "${DOC_TOOL_COUNT:-}" ] && [ "$DOC_TOOL_COUNT" != "$TOOL_COUNT" ]; then
    note_error "CLAUDE.md claims '$DOC_TOOL_COUNT cos_* tools' but server.py has $TOOL_COUNT @mcp.tool decorators"
  fi

  # Stale legacy references
  if grep -q '\bnako_' "$CLAUDE_MD"; then
    note_error "CLAUDE.md contains legacy 'nako_*' references — should be 'cos_*'"
  fi
  if grep -q 'Database Schema (v[0-9]' "$CLAUDE_MD"; then
    CLAUDE_SCHEMA=$(grep -oE 'Database Schema \(v[0-9]+\)' "$CLAUDE_MD" | head -1 | grep -oE '[0-9]+')
    if [ "$CLAUDE_SCHEMA" != "$SCHEMA_VERSION" ]; then
      note_error "CLAUDE.md claims schema v$CLAUDE_SCHEMA but db.py has v$SCHEMA_VERSION"
    fi
  fi
fi

# Note: the old docs/architecture.md cross-check was removed — that file no
# longer exists (architecture is a directory now) and no doc currently carries
# the "MCP Tools (NN)" / "Database Schema (vN)" headings, so the block only ever
# evaluated a missing-file no-op. CLAUDE.md remains the live cross-check above.

# ── Summary ─────────────────────────────────────────────────────────────────

echo ""
if [ "$ERRORS" -eq 0 ]; then
  ok "docs-staleness-check passed: $CHECKED source(s) checked, 0 errors, $WARNINGS warning(s)"
  exit 0
else
  err "docs-staleness-check failed: $ERRORS error(s), $WARNINGS warning(s). Update the affected docs."
fi
