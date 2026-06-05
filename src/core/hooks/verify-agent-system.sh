#!/usr/bin/env bash
# verify-agent-system.sh — Agent-agnostic ecosystem health check.
#
# Checks (in dependency order):
#   Layer 0: Foundation (config, state dir, hooks)
#   Layer 1: Gate system (thinking_os-gate, write-state)
#   Layer 2: Safety hooks (block-*.sh)
#   Layer 3: Skills (SKILL.md files)
#   Layer 4: MCP server (thinking_os DB)
#   Layer 5: Task system (tasks.md, changes.log)
#
# Exit: 0 = all pass, 1 = failures found

set -uo pipefail

source "$(dirname "$0")/cos-env.sh" 2>/dev/null || true

PROJECT_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$PROJECT_ROOT" || exit 1

# Narration (the full report) → stderr; the machine-parseable summary line
# goes to fd3 = the real stdout, so a caller can grep one clean PASS|WARN|FAIL.
exec 3>&1 1>&2

HOOKS_DIR="$(dirname "$0")"
PASS=0
FAIL=0
WARN=0
ERRORS=""

pass() { PASS=$((PASS + 1)); echo "  OK: $1"; }
fail() { FAIL=$((FAIL + 1)); ERRORS="${ERRORS}\n  FAIL: $1"; echo "  FAIL: $1"; }
warn() { WARN=$((WARN + 1)); echo "  WARN: $1"; }

echo "======================================================"
echo "  CODING-OS SYSTEM HEALTH CHECK"
echo "======================================================"
echo ""

# ── Layer 0: Foundation ──────────────────────────────────────────────
echo "--- Layer 0: Foundation ---"

# Config file
if [ -f ".coding-os.yaml" ]; then
  pass "Config file (.coding-os.yaml)"
else
  warn "No .coding-os.yaml — using defaults"
fi

# State directory
if [ -d "$COS_STATE_DIR" ]; then
  pass "State directory ($COS_STATE_DIR)"
else
  fail "State directory missing ($COS_STATE_DIR)"
fi

# Detect installed adapter (data-driven — checks every adapter probe path)
ADAPTER=""
if [ -f ".claude/settings.json" ]; then
  ADAPTER="claude"
  pass "Claude adapter installed (.claude/settings.json)"
fi
if [ -f ".codex/hooks.json" ]; then
  ADAPTER="${ADAPTER:+$ADAPTER+}codex"
  pass "Codex adapter installed (.codex/hooks.json)"
fi
if [ -d ".cursor/hooks" ]; then
  ADAPTER="${ADAPTER:+$ADAPTER+}cursor"
  pass "Cursor adapter installed (.cursor/hooks/)"
fi
if [ -z "$ADAPTER" ]; then
  warn "No adapter detected — run 'cos init -a <agent>' (claude / codex / cursor)"
fi

# AGENTS.md or CLAUDE.md
if [ -f "AGENTS.md" ] || [ -f "CLAUDE.md" ]; then
  pass "Router file (AGENTS.md/CLAUDE.md)"
else
  fail "No AGENTS.md or CLAUDE.md found"
fi

# write-state.sh
if [ -f "$HOOKS_DIR/write-state.sh" ]; then
  pass "write-state.sh exists"
  if [ -x "$HOOKS_DIR/write-state.sh" ] || bash -n "$HOOKS_DIR/write-state.sh" 2>/dev/null; then
    pass "write-state.sh is valid"
  else
    fail "write-state.sh has syntax errors"
  fi
else
  fail "write-state.sh missing"
fi

echo ""

# ── Layer 1: Gate System ─────────────────────────────────────────────
echo "--- Layer 1: Gate System ---"

GATE_HOOKS="thinking_os-gate.sh enforce-task-start.sh enforce-skill.sh enforce-zoom.sh enforce-verify.sh"
for hook in $GATE_HOOKS; do
  if [ -f "$HOOKS_DIR/$hook" ]; then
    if bash -n "$HOOKS_DIR/$hook" 2>/dev/null; then
      pass "$hook"
    else
      fail "$hook has syntax errors"
    fi
  else
    fail "$hook missing"
  fi
done

echo ""

# ── Layer 2: Safety Hooks ────────────────────────────────────────────
echo "--- Layer 2: Safety Hooks ---"

SAFETY_HOOKS="block-secrets.sh block-dangerous-commands.sh block-protected-files.sh block-bad-patterns.sh"
for hook in $SAFETY_HOOKS; do
  if [ -f "$HOOKS_DIR/$hook" ]; then
    if bash -n "$HOOKS_DIR/$hook" 2>/dev/null; then
      pass "$hook"
    else
      fail "$hook has syntax errors"
    fi
  else
    fail "$hook missing"
  fi
done

echo ""

# ── Layer 3: Skills ──────────────────────────────────────────────────
echo "--- Layer 3: Skills ---"

# Check for skills in any adapter dir
SKILL_COUNT=0
for skill_dir in .claude/skills .codex/skills .cursor/skills .coding-os/skills; do
  if [ -d "$skill_dir" ]; then
    count=$(ls "$skill_dir"/*/SKILL.md 2>/dev/null | wc -l | tr -d ' ')
    SKILL_COUNT=$((SKILL_COUNT + count))
  fi
done

if [ "$SKILL_COUNT" -gt 0 ]; then
  pass "$SKILL_COUNT skill(s) installed"
else
  warn "No skills found — install via adapter"
fi

echo ""

# ── Layer 4: MCP Server (Thinking OS) ────────────────────────────────
echo "--- Layer 4: Thinking OS DB ---"

if [ -f "$COS_DB_PATH" ]; then
  DB_SIZE=$(du -h "$COS_DB_PATH" | cut -f1)
  pass "Database exists ($DB_SIZE)"

  # Check schema version
  VERSION=$(python3 -c "
import sqlite3
c = sqlite3.connect('$COS_DB_PATH', timeout=2)
r = c.execute('SELECT MAX(version) FROM schema_version').fetchone()
print(r[0] if r and r[0] else 0)
c.close()
" 2>/dev/null || echo "0")

  if [ "$VERSION" -ge 4 ]; then
    pass "Schema version: v$VERSION"
  elif [ "$VERSION" -ge 1 ]; then
    warn "Schema version: v$VERSION (latest is v4)"
  else
    fail "Cannot read schema version"
  fi

  # Check table counts
  OUTCOMES=$(python3 -c "
import sqlite3
c = sqlite3.connect('$COS_DB_PATH', timeout=2)
r = c.execute('SELECT COUNT(*) FROM task_outcomes').fetchone()
print(r[0])
c.close()
" 2>/dev/null || echo "0")
  PATTERNS=$(python3 -c "
import sqlite3
c = sqlite3.connect('$COS_DB_PATH', timeout=2)
r = c.execute('SELECT COUNT(*) FROM learned_patterns').fetchone()
print(r[0])
c.close()
" 2>/dev/null || echo "0")
  echo "  Data: $OUTCOMES outcomes, $PATTERNS patterns"
else
  warn "No database at $COS_DB_PATH — will be created on first session"
fi

echo ""

# ── Layer 5: Task System ─────────────────────────────────────────────
echo "--- Layer 5: Task System ---"

if [ -d "docs/tasks" ]; then
  TASK_COUNT=$(find docs/tasks -maxdepth 1 -name 'TASK-*.md' 2>/dev/null | wc -l | tr -d ' ')
  pass "Scrumban tasks: $TASK_COUNT task file(s) in docs/tasks/"
else
  warn "No docs/tasks/ — create a task with 'cos task-create --title \"...\" --swimlane <lane> --kind <kind>'"
fi

if [ -f "changes.log" ]; then
  LOG_LINES=$(wc -l < changes.log | tr -d ' ')
  pass "Change log: $LOG_LINES lines"
else
  warn "No changes.log — will be created on first log-write"
fi

if [ -f "Makefile" ]; then
  pass "Makefile exists"
else
  warn "No Makefile — task management commands unavailable"
fi

echo ""

# ── Summary ──────────────────────────────────────────────────────────
echo "======================================================"
echo "  PASS: $PASS  |  WARN: $WARN  |  FAIL: $FAIL" >&3
echo "======================================================"

if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "Failures:"
  echo -e "$ERRORS"
  exit 1
fi

exit 0
